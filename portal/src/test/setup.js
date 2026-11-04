import '@testing-library/jest-dom/vitest'

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock
HTMLElement.prototype.hasPointerCapture ||= () => false
HTMLElement.prototype.setPointerCapture ||= () => {}
HTMLElement.prototype.releasePointerCapture ||= () => {}
HTMLElement.prototype.scrollIntoView ||= () => {}
globalThis.URL.createObjectURL = () => 'blob:mock-qr'
globalThis.URL.revokeObjectURL = () => {}
