'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { FolderOpen, LogOut, Upload } from 'lucide-react'
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
          <Link href="/" className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/akashi-logo.svg" alt="AKASHI DATA CENTER" className="w-9 h-9" />
            <span className="flex flex-col leading-tight">
              <span className="font-semibold text-neutral-900">AKASHI DATA CENTER</span>
              <span className="text-xs text-neutral-500">Compliance Workspace</span>
            </span>
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
