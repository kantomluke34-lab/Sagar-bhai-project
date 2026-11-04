import * as Tooltip from '@radix-ui/react-tooltip'

export default function Hint({ label, children }) {
  return <Tooltip.Provider delayDuration={250}>
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal><Tooltip.Content className="hint-content" sideOffset={6}>{label}<Tooltip.Arrow className="hint-arrow" /></Tooltip.Content></Tooltip.Portal>
    </Tooltip.Root>
  </Tooltip.Provider>
}
