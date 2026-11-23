import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { useEffect, useState } from 'react'

export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  expectedValue = '',
  expectedLabel = 'Type the exact name to confirm',
  busy = false,
}) {
  const [confirmation, setConfirmation] = useState('')
  const [actionError, setActionError] = useState('')

  useEffect(() => {
    if (!open) { setConfirmation(''); setActionError('') }
  }, [open])

  const confirmed = !expectedValue || confirmation === expectedValue

  return <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
    <AlertDialog.Portal>
      <AlertDialog.Overlay className="dialog-overlay" />
      <AlertDialog.Content className="confirm-dialog">
        <AlertDialog.Title>{title}</AlertDialog.Title>
        <AlertDialog.Description>{description}</AlertDialog.Description>
        {expectedValue && <label>{expectedLabel}: <strong>{expectedValue}</strong><input autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>}
        {actionError && <div className="alert error" role="alert">{actionError}</div>}
        <div className="dialog-actions">
          <AlertDialog.Cancel asChild><button className="secondary-button" disabled={busy}>Cancel</button></AlertDialog.Cancel>
          <AlertDialog.Action asChild><button className="danger-button" disabled={busy || !confirmed} onClick={async (event) => { event.preventDefault(); setActionError(''); try { await onConfirm() } catch (error) { setActionError(error?.message || 'The action could not be completed.') } }}>{busy ? 'Working…' : confirmLabel}</button></AlertDialog.Action>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>
}
