import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

export default function Drawer({ open, onOpenChange, kicker, title, description, className = '', children, footer }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="drawer-backdrop" />
      <Dialog.Content className={`drawer ${className}`.trim()}>
        <Dialog.Close asChild><button className="drawer-close" aria-label={`Close ${title}`}><X /></button></Dialog.Close>
        {kicker && <span className="eyebrow">{kicker}</span>}
        <Dialog.Title>{title}</Dialog.Title>
        {description && <Dialog.Description>{description}</Dialog.Description>}
        <div className="drawer-body">{children}</div>
        {footer && <footer className="drawer-footer">{footer}</footer>}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
