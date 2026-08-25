import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ClerkProvider } from '@clerk/react'
import { neobrutalism } from '@clerk/ui/themes'

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || ''

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={clerkPublishableKey}
      appearance={{
        theme: neobrutalism,
      }}
    >
      <App />
    </ClerkProvider>
  </StrictMode>,
)
