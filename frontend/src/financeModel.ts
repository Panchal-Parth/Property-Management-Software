import { useState } from 'react'
export const keys = ['rent', 'water', 'repairs', 'misc', 'insurance', 'tax'] as const
export type Amounts = Record<typeof keys[number], number>
export type Entry = Amounts & { propertyId: number; month: string }
const initialEntries: Entry[] = [
  { propertyId: 1, month: '2024-06', rent: 18400, water: 620, repairs: 1240, misc: 280, insurance: 410, tax: 320 },
  { propertyId: 2, month: '2024-06', rent: 9200, water: 280, repairs: 640, misc: 180, insurance: 360, tax: 210 },
  { propertyId: 3, month: '2024-06', rent: 6800, water: 220, repairs: 1940, misc: 160, insurance: 150, tax: 110 },
]
export function useFinances() {
  const [entries, setEntries] = useState(initialEntries)
  const [categories, setCategories] = useState(['Insurance', 'Property tax'])
  return { entries, setEntries, categories, setCategories }
}
