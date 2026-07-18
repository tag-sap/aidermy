'use client'

import { useState } from 'react'
import { ChevronRight, ChevronLeft, Sparkles, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SkinQuizProps {
  onComplete: (answers: Record<string, string>, skinType: string) => void
  onCancel?: () => void
  initialAnswers?: Record<string, string>
}

const QUESTIONS = [
  {
    id: 'feel_after_wash',
    question: 'Как чувствуется кожа сразу после умывания?',
    options: [
      { value: 'tight', label: 'Стянутая, сухая' },
      { value: 'normal', label: 'Комфортная, мягкая' },
      { value: 'oily', label: 'Жирная, блестящая' },
      { value: 'mixed', label: 'Т-зона жирная, щеки сухие' },
    ]
  },
  {
    id: 'skin_reaction',
    question: 'Как кожа реагирует на новую косметику?',
    options: [
      { value: 'sensitive', label: 'Часто появляется покраснение или жжение' },
      { value: 'sometimes', label: 'Иногда, но редко' },
      { value: 'never', label: 'Никак, хорошо переносит' },
    ]
  },
  {
    id: 'moisture_level',
    question: 'Как часто кожа ощущается сухой в течение дня?',
    options: [
      { value: 'always', label: 'Почти всегда сухая' },
      { value: 'sometimes', label: 'Иногда, особенно зимой' },
      { value: 'rarely', label: 'Редко, кожа хорошо увлажнена' },
      { value: 'oily', label: 'Наоборот, быстро становится жирной' },
    ]
  },
  {
    id: 'pores',
    question: 'Какие у вас поры?',
    options: [
      { value: 'small', label: 'Мелкие, почти незаметные' },
      { value: 'medium', label: 'Средние, заметны в Т-зоне' },
      { value: 'large', label: 'Крупные, заметные везде' },
    ]
  }
]

export function SkinQuiz({ onComplete, onCancel, initialAnswers = {} }: SkinQuizProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>(initialAnswers)

  const question = QUESTIONS[currentStep]
  const allAnswered = QUESTIONS.every(q => answers[q.id])

  const handleAnswer = (value: string) => {
    setAnswers(prev => ({ ...prev, [question.id]: value }))
  }

  const handleNext = () => {
    if (currentStep < QUESTIONS.length - 1) {
      setCurrentStep(prev => prev + 1)
    } else if (allAnswered) {
      // Все вопросы отвечены - определяем тип кожи
      const skinType = determineSkinType(answers)
      onComplete(answers, skinType)
    }
  }

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1)
    }
  }

  const determineSkinType = (answers: Record<string, string>): string => {
    const feel = answers.feel_after_wash || ''
    const reaction = answers.skin_reaction || ''
    const moisture = answers.moisture_level || ''
    const pores = answers.pores || ''

    if (feel === 'tight' && moisture === 'always') return 'Сухая'
    if (feel === 'oily' && moisture === 'oily') return 'Жирная'
    if (feel === 'mixed' && moisture === 'sometimes') return 'Комбинированная'
    if (reaction === 'sensitive') return 'Чувствительная'
    if (feel === 'normal' && moisture === 'rarely') return 'Нормальная'
    if (feel === 'tight' && reaction === 'sensitive') return 'Сухая чувствительная'
    if (feel === 'oily' && pores === 'large') return 'Жирная с расширенными порами'
    
    return 'Нормальная'
  }

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
        {/* Прогресс */}
        <div className="flex gap-1 mb-4">
          {QUESTIONS.map((_, i) => (
            <div
              key={i}
              className={cn(
                'flex-1 h-1.5 rounded-full transition-all',
                i < currentStep || (i === currentStep && answers[question?.id]) 
                  ? 'bg-primary' 
                  : 'bg-gray-200'
              )}
            />
          ))}
        </div>

        {/* Вопрос */}
        <div className="mb-6">
          <p className="text-xs text-gray-400 mb-1">
            Вопрос {currentStep + 1} из {QUESTIONS.length}
          </p>
          <h4 className="text-base font-semibold text-gray-900">
            {question?.question}
          </h4>
        </div>

        {/* Варианты ответов */}
        <div className="space-y-2">
          {question?.options.map((option) => (
            <button
              key={option.value}
              onClick={() => handleAnswer(option.value)}
              className={cn(
                'w-full text-left px-4 py-3 rounded-lg border transition-all text-sm',
                answers[question.id] === option.value
                  ? 'border-primary bg-primary/5 text-primary font-medium'
                  : 'border-gray-200 hover:border-primary/30 hover:bg-gray-50'
              )}
            >
              <div className="flex items-center justify-between">
                <span>{option.label}</span>
                {answers[question.id] === option.value && (
                  <Check className="size-4 text-primary" />
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Навигация */}
        <div className="flex gap-3 mt-6">
          <button
            onClick={onCancel || handlePrevious}
            className={cn(
              'px-4 py-2.5 rounded-lg text-sm font-medium transition-all',
              currentStep === 0 && !onCancel
                ? 'text-gray-300 cursor-not-allowed'
                : 'text-gray-600 hover:bg-gray-50'
            )}
            disabled={currentStep === 0 && !onCancel}
          >
            {onCancel ? 'Отмена' : 'Назад'}
          </button>
          <button
            onClick={handleNext}
            disabled={!answers[question?.id]}
            className={cn(
              'flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all flex items-center justify-center gap-1',
              answers[question?.id]
                ? 'bg-primary hover:bg-primary/90'
                : 'bg-gray-300 cursor-not-allowed'
            )}
          >
            {currentStep === QUESTIONS.length - 1 ? (
              <>
                <Sparkles className="size-4" />
                Определить тип кожи
              </>
            ) : (
              <>
                Далее
                <ChevronRight className="size-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}