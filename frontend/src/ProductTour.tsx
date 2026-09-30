import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, X } from 'lucide-react'

export type TourStep = {
  page: string
  target: string
  eyebrow: string
  title: string
  description: string
}

type Rect = { top: number; left: number; width: number; height: number }

export default function ProductTour({ step, steps, onBack, onNext, onClose }: {
  step: number
  steps: TourStep[]
  onBack: () => void
  onNext: () => void
  onClose: () => void
}) {
  const [rect, setRect] = useState<Rect | null>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const current = steps[step]

  useLayoutEffect(() => {
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const element = document.querySelector<HTMLElement>(current.target)
        if (!element) { setRect(null); return }
        element.scrollIntoView({ block: 'center', behavior: 'smooth' })
        const box = element.getBoundingClientRect()
        setRect({ top: Math.max(8, box.top - 8), left: Math.max(8, box.left - 8), width: Math.min(innerWidth - 16, box.width + 16), height: box.height + 16 })
      })
    }
    const timer = window.setTimeout(update, 40)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => { clearTimeout(timer); cancelAnimationFrame(frame); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [current])

  useEffect(() => {
    cardRef.current?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowRight') onNext()
      if (event.key === 'ArrowLeft' && step > 0) onBack()
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [onBack, onClose, onNext, step])

  const cardStyle = rect && innerWidth > 700 ? {
    top: Math.min(innerHeight - 330, Math.max(20, rect.top + rect.height + 18)),
    left: Math.min(innerWidth - 400, Math.max(260, rect.left)),
  } : undefined
  const last = step === steps.length - 1

  return <div className="tour" role="presentation">
    <div className="tour-backdrop" />
    {rect && <div className="tour-spotlight" style={rect} aria-hidden="true" />}
    <div ref={cardRef} className="tour-card" style={cardStyle} role="dialog" aria-modal="true" aria-labelledby="tour-title" tabIndex={-1}>
      <div className="tour-card-top"><span>{current.eyebrow}</span><button type="button" className="tour-close" onClick={onClose} aria-label="Close tutorial"><X size={19} /></button></div>
      <div className="tour-progress" aria-label={`Tutorial step ${step + 1} of ${steps.length}`}><i style={{ width: `${((step + 1) / steps.length) * 100}%` }} /></div>
      <p className="tour-count">STEP {step + 1} OF {steps.length}</p>
      <h2 id="tour-title">{current.title}</h2>
      <p>{current.description}</p>
      <div className="tour-actions"><button type="button" className="text-btn" onClick={onClose}>Skip tour</button><div>{step > 0 && <button type="button" className="secondary-btn" onClick={onBack}><ArrowLeft size={16} />Back</button>}<button type="button" className="primary-btn" onClick={onNext}>{last ? <><Check size={17} />Finish</> : <>Next<ArrowRight size={16} /></>}</button></div></div>
    </div>
  </div>
}
