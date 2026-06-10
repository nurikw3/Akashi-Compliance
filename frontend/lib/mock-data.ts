import type { Assessment, Case, EnrichmentData } from './types'

export type { Assessment, Case, ChatMessage, Document, EnrichmentData } from './types'

// Simple seeded random for deterministic mock data
function seededRandom(seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash
  }
  return Math.abs((Math.sin(hash) * 10000) % 1)
}

// Mock enrichment data generator
export function generateMockEnrichment(name: string, iinBin: string): EnrichmentData {
  const random = seededRandom(iinBin)
  const hasDebt = random > 0.6
  const hasCourts = random > 0.5
  const hasSanctions = random > 0.9

  return {
    companyInfo: {
      fullName: `ТОО "${name}"`,
      registrationDate: '2018-03-15',
      address: 'г. Алматы, ул. Абая, д. 52, офис 301',
      director: 'Иванов Сергей Петрович',
      employees: Math.floor(seededRandom(iinBin + 'emp') * 200) + 10,
      industry: ['IT', 'Строительство', 'Торговля', 'Производство', 'Услуги'][Math.floor(seededRandom(iinBin + 'ind') * 5)],
    },
    taxes: {
      debt: hasDebt ? Math.floor(seededRandom(iinBin + 'debt') * 5000000) + 100000 : 0,
      lastPayment: '2024-01-15',
      status: hasDebt ? (random > 0.8 ? 'critical' : 'debt') : 'clean',
    },
    courts: {
      activeCases: hasCourts ? Math.floor(seededRandom(iinBin + 'court') * 3) + 1 : 0,
      completedCases: Math.floor(seededRandom(iinBin + 'comp') * 5),
      totalAmount: hasCourts ? Math.floor(seededRandom(iinBin + 'amount') * 10000000) : 0,
      cases: hasCourts
        ? [
            { type: 'Гражданское', amount: 2500000, date: '2024-02-10', status: 'В процессе' },
            { type: 'Административное', amount: 150000, date: '2023-11-05', status: 'Завершено' },
          ]
        : [],
    },
    sanctions: {
      isOnList: hasSanctions,
      lists: hasSanctions ? ['OFAC SDN List'] : [],
    },
    affiliates: {
      companies: [
        { name: 'ТОО "Альфа Групп"', iinBin: '123456789012', role: 'Учредитель' },
        { name: 'ТОО "Бета Сервис"', iinBin: '987654321098', role: 'Директор' },
      ],
      individuals: [
        { name: 'Иванов С.П.', iin: '850101350123', role: 'Директор' },
        { name: 'Петров А.Н.', iin: '900515400456', role: 'Учредитель (30%)' },
      ],
    },
  }
}

export function generateMockAssessment(enrichment: EnrichmentData): Assessment {
  const flags: Assessment['flags'] = []

  if (enrichment.taxes.debt > 0) {
    flags.push({
      type: 'fact',
      message: `Налоговая задолженность: ${enrichment.taxes.debt.toLocaleString()} тг`,
    })
  }

  if (enrichment.courts.activeCases > 0) {
    flags.push({
      type: 'fact',
      message: `Активные судебные дела: ${enrichment.courts.activeCases}`,
    })
  }

  if (enrichment.sanctions.isOnList) {
    flags.push({
      type: 'fact',
      message: `Компания в санкционном списке: ${enrichment.sanctions.lists.join(', ')}`,
    })
  }

  return { flags }
}

// Initial mock cases
export const initialMockCases: Case[] = [
  {
    id: '1',
    name: 'КазСтройИнвест',
    iinBin: '180340021234',
    status: 'ready',
    createdAt: new Date('2024-01-15'),
    enrichment: generateMockEnrichment('КазСтройИнвест', '180340021234'),
    assessment: undefined,
    documents: [],
    chatHistory: [],
  },
  {
    id: '2',
    name: 'ТехноПром',
    iinBin: '150240015678',
    status: 'ready',
    createdAt: new Date('2024-01-14'),
    enrichment: generateMockEnrichment('ТехноПром', '150240015678'),
    assessment: undefined,
    documents: [],
    chatHistory: [],
  },
  {
    id: '3',
    name: 'АльфаТрейд',
    iinBin: '200140029012',
    status: 'ready',
    createdAt: new Date('2024-01-13'),
    enrichment: generateMockEnrichment('АльфаТрейд', '200140029012'),
    assessment: undefined,
    documents: [],
    chatHistory: [],
  },
  {
    id: '4',
    name: 'МегаЛогистик',
    iinBin: '170540033456',
    status: 'enriching',
    createdAt: new Date('2024-01-12'),
    enrichment: undefined,
    assessment: undefined,
    documents: [],
    chatHistory: [],
  },
]

// Add assessments to ready cases
initialMockCases.forEach((c) => {
  if (c.enrichment) {
    c.assessment = generateMockAssessment(c.enrichment)
  }
})
