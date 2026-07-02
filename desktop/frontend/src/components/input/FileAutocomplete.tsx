// Placeholder for file autocomplete component.
// In the full implementation, this would query the backend for file listings
// and provide fuzzy-matched completions when typing @ or file paths.

interface Props {
  filter: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function FileAutocomplete({ filter: _filter, onSelect: _onSelect, onClose: _onClose }: Props) {
  // Stub — file completion requires backend integration
  return null;
}
