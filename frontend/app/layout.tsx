import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { AuthGate } from '@/components/auth-gate'
import { CasesProvider } from '@/lib/cases-context'
import { Header } from '@/components/header'
import './globals.css'

const inter = Inter({ subsets: ['latin', 'cyrillic'] })

export const metadata: Metadata = {
  title: 'Compliance Workspace',
  description: 'Платформа для проверки контрагентов',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="ru" className="bg-neutral-50">
      <body className={`${inter.className} antialiased`}>
        <AuthGate>
          <CasesProvider>
            <Header />
            <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
              {children}
            </main>
          </CasesProvider>
        </AuthGate>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
