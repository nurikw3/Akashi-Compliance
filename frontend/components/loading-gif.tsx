import Image from 'next/image'

type LoadingGifProps = {
  message?: string
  size?: number
  className?: string
}

export function LoadingGif({ message, size = 160, className = '' }: LoadingGifProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 py-16 ${className}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Image
        src="/loading.gif"
        alt=""
        width={size}
        height={size}
        unoptimized
        priority
        className="rounded-lg"
      />
      {message && <p className="text-sm text-neutral-500">{message}</p>}
    </div>
  )
}
