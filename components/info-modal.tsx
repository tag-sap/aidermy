'use client'

import { X, Sparkles, Shield, Zap, Users, Brain } from 'lucide-react'

interface InfoModalProps {
  isOpen: boolean
  onClose: () => void
}

export function InfoModal({ isOpen, onClose }: InfoModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl max-w-md w-full max-h-[90vh] overflow-y-auto p-6 relative animate-in fade-in zoom-in duration-200">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <X className="size-5" />
        </button>

        <div className="text-center mb-6">
          <div className="text-5xl mb-3">🧴</div>
          <h2 className="text-2xl font-bold text-gray-900">Как работает Aidermy?</h2>
        </div>

        <div className="space-y-4">
          <div className="flex gap-3 p-3 bg-gray-50 rounded-xl">
            <Brain className="size-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-gray-900 text-sm">1. AI-анализ состава</h4>
              <p className="text-sm text-gray-600">
                Искусственный интеллект анализирует каждый ингредиент продукта и оценивает его совместимость с вашей кожей.
              </p>
            </div>
          </div>

          <div className="flex gap-3 p-3 bg-gray-50 rounded-xl">
            <Shield className="size-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-gray-900 text-sm">2. Проверка безопасности</h4>
              <p className="text-sm text-gray-600">
                Мы предупреждаем о потенциально опасных ингредиентах и компонентах, которые могут вызвать раздражение.
              </p>
            </div>
          </div>

          <div className="flex gap-3 p-3 bg-gray-50 rounded-xl">
            <Zap className="size-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-gray-900 text-sm">3. Мгновенный результат</h4>
              <p className="text-sm text-gray-600">
                Получите оценку совместимости, подробный разбор состава и персональные рекомендации за секунды.
              </p>
            </div>
          </div>

          <div className="flex gap-3 p-3 bg-gray-50 rounded-xl">
            <Users className="size-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-gray-900 text-sm">4. Для всех типов кожи</h4>
              <p className="text-sm text-gray-600">
                Подходит для сухой, жирной, комбинированной и чувствительной кожи. Подбирайте косметику с умом!
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={onClose}
          className="w-full mt-6 py-3 bg-primary text-white font-medium rounded-xl hover:bg-primary/90 transition-colors"
        >
          Понятно, спасибо!
        </button>
      </div>
    </div>
  )
}
