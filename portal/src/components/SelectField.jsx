import * as Select from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'

const EMPTY = '__empty_option__'

export default function SelectField({ value, onChange, options, placeholder = 'Select an option', 'aria-label': ariaLabel, disabled = false }) {
  return <Select.Root value={value === '' ? EMPTY : String(value)} onValueChange={(next) => onChange(next === EMPTY ? '' : next)} disabled={disabled}>
    <Select.Trigger className="custom-select" aria-label={ariaLabel}>
      <Select.Value placeholder={placeholder} />
      <Select.Icon><ChevronDown size={16} aria-hidden="true" /></Select.Icon>
    </Select.Trigger>
    <Select.Portal>
      <Select.Content className="custom-select-content" position="popper" sideOffset={5} collisionPadding={8}>
        <Select.Viewport className="custom-select-viewport">
          {options.map((option) => {
            const item = typeof option === 'string' ? { value: option, label: option } : option
            return <Select.Item className="custom-select-item" key={item.value} value={item.value === '' ? EMPTY : String(item.value)}>
              <Select.ItemText>{item.label}</Select.ItemText>
              <Select.ItemIndicator className="custom-select-indicator"><Check size={15} aria-hidden="true" /></Select.ItemIndicator>
            </Select.Item>
          })}
        </Select.Viewport>
      </Select.Content>
    </Select.Portal>
  </Select.Root>
}
