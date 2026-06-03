# Compliance Workspace — MVP Prompt для Cursor

## Контекст
Готов React фронтенд (загрузка Excel, dashboard дел, страница компании с вкладками: Граф связей, Документы, Заключение, Загрузка PDF отчета из сервисов, ИИ, Чат с ИИ)

Задача: построить бэкенд с чистой архитектурой, где Adata — это первый из многих провайдеров данных, а не центр системы.

---

## Главный принцип архитектуры

Система не знает про Adata. Система знает про **Provider** — абстрактный источник данных о компании. Adata, Kompra, egov.kz, любой новый сервис — это просто реализации одного интерфейса.

```
                    ┌─────────────────────┐
                    │   Provider Interface │
                    │  check(iin) → Data  │
                    └─────────────────────┘
                     ↙        ↓         ↘
              Adata       Kompra       egov.kz
              Provider    Provider     Provider
```

Добавить новый источник = написать один класс, зарегистрировать в реестре. Больше ничего не трогать.

---

## Стек

**Бэкенд:** FastAPI (Python)
**БД:** PostgreSQL (дела, документы, чат)
**Граф:** Neo4j (связи между компаниями и людьми)
**Очередь:** Celery + Redis
**ИИ:** OpenAI (с выбором base_url , model)

---

## Архитектура бэкенда

```
backend/app/
  api/routes/          # HTTP endpoints — только роутинг, логики нет
  
  services/
    enrichment/        # ← ВСЁ про внешние источники данных
      base.py          # BaseProvider (абстракция)
      registry.py      # ProviderRegistry
      providers/
        adata.py
        kompra.py      # добавить позже — только этот файл
        egov.py        # добавить позже — только этот файл
    
    graph/             # работа с Neo4j
    ai/                # OpenAI: заключения, чат, анализ документов
    risk/              # расчёт риска (независим от источника)
  
  workers/tasks.py     # Celery задачи
  models/              # SQLAlchemy + Pydantic схемы
  core/config.py       # настройки через env
```

---

## Ключевой код: Provider Interface

### base.py
```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional

class CompanyData(BaseModel):
    """Единая модель данных — не зависит от источника"""
    iin: str
    name: Optional[str]
    status: Optional[str]          # active / liquidated / suspended
    tax_debt: Optional[float]
    court_cases: Optional[int]
    in_sanctions_list: Optional[bool]
    director: Optional[str]
    founders: list[dict] = []
    related_companies: list[dict] = []
    raw: dict = {}                 # оригинальный ответ провайдера

class BaseProvider(ABC):
    name: str  # "adata", "kompra", etc.

    @abstractmethod
    async def check(self, iin: str) -> CompanyData:
        """Запросить данные по ИИН и вернуть в единой модели"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Провайдер доступен (ключ настроен, сервис жив)"""
        ...
```

### registry.py
```python
class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider):
        self._providers[provider.name] = provider

    def get(self, name: str) -> BaseProvider:
        return self._providers[name]

    def available(self) -> list[BaseProvider]:
        return [p for p in self._providers.values() if p.is_available()]

# Singleton
registry = ProviderRegistry()
```

### providers/adata.py
```python
class AdataProvider(BaseProvider):
    name = "adata"

    async def check(self, iin: str) -> CompanyData:
        raw = await self._call_api(iin)
        # Маппинг ответа Adata → единую модель CompanyData
        return CompanyData(
            iin=iin,
            status=raw.get("organizationStatus"),
            tax_debt=raw.get("taxDebt"),
            # ... маппинг полей Adata
            raw=raw
        )
```

### Добавление нового провайдера (пример Kompra)
```python
# providers/kompra.py — ТОЛЬКО этот файл
class KompraProvider(BaseProvider):
    name = "kompra"

    async def check(self, iin: str) -> CompanyData:
        raw = await self._call_api(iin)
        return CompanyData(
            iin=iin,
            status=raw.get("status"),  # маппинг под Kompra
            ...
            raw=raw
        )

# main.py — одна строка
registry.register(KompraProvider())
```

Больше нигде ничего не меняется.

---

## Сервис обогащения (enrichment service)

```python
class EnrichmentService:
    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    async def enrich(self, iin: str) -> list[CompanyData]:
        """Запрашивает все доступные провайдеры параллельно"""
        providers = self.registry.available()
        results = await asyncio.gather(
            *[p.check(iin) for p in providers],
            return_exceptions=True
        )
        return [r for r in results if isinstance(r, CompanyData)]

    def merge(self, results: list[CompanyData]) -> CompanyData:
        """Мерджит данные из нескольких источников.
        Приоритет: первый непустой ответ для каждого поля."""
        merged = CompanyData(iin=results[0].iin)
        for result in results:
            for field in CompanyData.model_fields:
                if getattr(merged, field) is None:
                    setattr(merged, field, getattr(result, field))
        return merged
```

---

## Risk Service (независим от провайдеров)

```python
# Принимает CompanyData — не важно откуда она пришла
class RiskService:
    def calculate(self, data: CompanyData) -> RiskLevel:
        score = 0
        if data.in_sanctions_list:
            return RiskLevel.HIGH  # сразу
        if data.tax_debt and data.tax_debt > 1_000_000:
            score += 3
        if data.court_cases and data.court_cases > 3:
            score += 2
        if data.status in ["liquidated", "suspended"]:
            score += 4
        return RiskLevel.HIGH if score >= 5 else RiskLevel.MEDIUM if score >= 2 else RiskLevel.LOW
```

---

## Graph Service (Neo4j)

```python
# Принимает CompanyData — не важно откуда
class GraphService:
    async def upsert_company(self, data: CompanyData):
        await self.neo4j.run("""
            MERGE (c:Company {iin: $iin})
            SET c.name = $name, c.status = $status
        """, iin=data.iin, name=data.name, status=data.status)

        for founder in data.founders:
            await self.neo4j.run("""
                MERGE (p:Person {iin: $iin})
                MERGE (p)-[:FOUNDER_OF {share: $share}]->(c:Company {iin: $company_iin})
            """, **founder, company_iin=data.iin)
```

---

## Celery Worker

```python
@celery.task
async def check_company(case_id: str, iin: str):
    # 1. Обогатить через все доступные провайдеры
    results = await enrichment_service.enrich(iin)
    merged = enrichment_service.merge(results)

    # 2. Сохранить в Postgres
    await case_repo.update(case_id, data=merged)

    # 3. Записать граф в Neo4j
    await graph_service.upsert_company(merged)

    # 4. Рассчитать риск
    risk = risk_service.calculate(merged)
    await case_repo.set_risk(case_id, risk)

    # 5. Сгенерировать заключение
    await ai_service.generate_conclusion(case_id, merged)
```

---

## AI Service

```python
class AIService:
    CONCLUSION_PROMPT = """
Ты compliance-ассистент. Данные проверки контрагента:
{data}

Дай заключение:
1. Общий вывод (1 предложение)
2. Ключевые факты
3. Риски и красные флаги
4. Рекомендация: Одобрить / Запросить документы / Отказать

Отвечай на русском. Только факты из данных.
"""

    CHAT_SYSTEM_PROMPT = """
Ты compliance-ассистент. Контекст дела:
Компания: {company_data}
Заключение: {conclusion}
Документы: {documents}

Отвечай на вопросы офицера. Составляй служебные записки, запросы, сравнения.
"""
```

---

## API Endpoints

```
POST   /api/upload                      # загрузка Excel
GET    /api/cases                       # список дел
GET    /api/cases/{id}                  # данные дела
GET    /api/cases/{id}/graph            # граф для фронта
GET    /api/cases/{id}/conclusion       # заключение ИИ
POST   /api/cases/{id}/chat             # чат (SSE streaming)
POST   /api/cases/{id}/documents        # загрузка документа
GET    /api/providers                   # какие провайдеры активны
```

---

## PostgreSQL схема

```sql
CREATE TABLE cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name VARCHAR,
    iin VARCHAR NOT NULL,
    status VARCHAR DEFAULT 'pending',  -- pending/processing/done/error
    risk_level VARCHAR,
    enriched_data JSONB,               -- merged CompanyData
    sources JSONB DEFAULT '[]',        -- какие провайдеры ответили
    conclusion TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE,
    filename VARCHAR,
    analysis TEXT,
    uploaded_at TIMESTAMP DEFAULT now()
);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE,
    role VARCHAR,  -- user / assistant
    content TEXT,
    created_at TIMESTAMP DEFAULT now()
);
```

---

## Docker Compose

См. актуальный `docker-compose.yml` в корне репозитория:

- **FRONTEND_HOST_PORT** (по умолчанию `8000`) — единственный порт на хосте → Next.js
- **API** — `API_PORT` (по умолчанию `8000`) только внутри сети compose (`http://api:8000`)
- **postgres**, **redis**, **worker** — без publish на хост

---

## ENV

```
# Провайдеры (добавляй новые сюда)
ADATA_API_KEY=
ADATA_BASE_URL=
KOMPRA_API_KEY=         # когда подключишь
KOMPRA_BASE_URL=        # когда подключишь

# ИИ
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=

# Инфра
DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=
```

---

## Что НЕ делать в MVP

- Авторизация
- Экспорт PDF
- Мониторинг изменений контрагентов
- Мобильная версия