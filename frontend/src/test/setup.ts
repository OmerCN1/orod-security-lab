import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Without `globals: true`, React Testing Library does not register its own cleanup, so
// rendered trees would accumulate across tests and queries would match several elements.
afterEach(cleanup)
