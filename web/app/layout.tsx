import type { Metadata } from 'next'
import { QueryProvider } from '@/context/query-client'
import { Toaster } from '@/components/ui/sonner'
import '@/styles/globals.css'
import '@/styles/_variables.scss'
import '@/styles/_keyframe-animations.scss'
import 'yet-another-react-lightbox/styles.css'
import 'yet-another-react-lightbox/plugins/thumbnails.css'
import 'jit-viewer/style.css'
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
  title: 'OpenDesk',
  description: 'OpenDesk - Customer Service Platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={cn("font-sans", geist.variable)} suppressHydrationWarning>
      <body suppressHydrationWarning>
        <QueryProvider>{children}</QueryProvider>
        <Toaster position="top-right" richColors closeButton />
      </body>
    </html>
  )
}
