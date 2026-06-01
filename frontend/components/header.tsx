'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { FolderOpen, LogOut, Shield, Upload } from 'lucide-react'
import { clearAuth } from '@/lib/auth'

export function Header() {
  const pathname = usePathname()
  const router = useRouter()

  function handleLogout() {
    clearAuth()
    router.refresh()
    window.location.href = '/'
  }

  const links = [
    { href: '/#bin-text', label: 'Загрузка', icon: Upload },
    { href: '/cases', label: 'Контрагенты', icon: FolderOpen },
  ]

  return (
    <header className="bg-white border-b border-neutral-200">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold text-neutral-900">Compliance Workspace</span>
          </Link>

          <nav className="flex items-center gap-1">
            {links.map((link) => {
              const Icon = link.icon
              const isActive = pathname === link.href || (link.href !== '/' && pathname.startsWith(link.href))
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-600'
                      : 'text-neutral-600 hover:bg-neutral-100'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {link.label}
                </Link>
              )
            })}
            <button
              type="button"
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-neutral-600 hover:bg-neutral-100 transition-colors ml-2"
            >
              <LogOut className="w-4 h-4" />
              Выйти
            </button>
          </nav>
        </div>
      </div>
    </header>
  )
}
