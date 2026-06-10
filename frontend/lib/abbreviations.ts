// Central glossary of abbreviations / compliance terms.
// Mirrors the backend `app/services/glossary.py` — keep both in sync.

export const GLOSSARY: Record<string, string> = {
  // KZ business / legal
  'БИН': 'Бизнес-идентификационный номер (12 цифр) юридического лица',
  'ИИН': 'Индивидуальный идентификационный номер (12 цифр) физического лица',
  'ОПФ': 'Организационно-правовая форма юридического лица',
  'ТОО': 'Товарищество с ограниченной ответственностью',
  'АО': 'Акционерное общество',
  'ИП': 'Индивидуальный предприниматель',
  'КГД': 'Комитет государственных доходов (налоговый орган РК)',
  'КФМ': 'Комитет по финансовому мониторингу (финансовая разведка РК)',
  'УБО': 'Конечный бенефициарный собственник (Ultimate Beneficial Owner)',
  'UBO': 'Конечный бенефициарный собственник (Ultimate Beneficial Owner)',
  'ЧСИ': 'Частный судебный исполнитель',
  // International sanctions / screening
  'LSEG': 'London Stock Exchange Group — поставщик данных World-Check One',
  'WC1': 'World-Check One — база санкций, PEP и негативных публикаций (LSEG)',
  'PEP': 'Politically Exposed Person — публичное должностное лицо',
  'OFAC': 'Office of Foreign Assets Control — орган санкций Минфина США',
  'SDN': 'Specially Designated Nationals — санкционный список OFAC (США)',
  'HMT': "His Majesty's Treasury — орган санкций Великобритании",
  'EU': 'European Union — санкционные списки Европейского союза',
  'UN': 'United Nations — санкционные списки ООН',
  'SECO': 'State Secretariat for Economic Affairs — санкции Швейцарии',
  'FATF': 'Financial Action Task Force — меры борьбы с отмыванием денег',
  'AML': 'Anti-Money Laundering — противодействие отмыванию денег',
  'CFT': 'Combating the Financing of Terrorism — противодействие финансированию терроризма',
  'KYC': 'Know Your Customer — процедуры идентификации клиента',
  // Data sources / terms
  'Adata': 'Adata.kz — источник данных по компаниям Казахстана',
  'Контроль и надзор':
    'Сведения о государственном контроле и надзоре — проверки, предписания и надзорные меры государственных органов в отношении контрагента (по данным Adata)',
}

export function defineTerm(term: string): string | undefined {
  return GLOSSARY[term]
}
