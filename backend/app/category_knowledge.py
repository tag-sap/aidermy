# category_knowledge.py
# База знаний категорий косметики для генерации отчёта LLM.
#
# Единый базовый промпт + структурированные знания о каждой категории.
# Категория определяет КОНТЕКСТ и релевантность объяснения, НЕ множитель score.
# Хранится версионируемым файлом (миграция в БД возможна позже без изменения
# Score Engine). Ключ = "body_area:subcategory_key" канонической таксономии
# (catalog_taxonomy.TAXONOMY).

from __future__ import annotations

from typing import Any, Dict

CATEGORY_KNOWLEDGE_VERSION = "1.0.0"

# Общая осторожная инструкция для неизвестной/неподдерживаемой категории.
FALLBACK_CATEGORY_KNOWLEDGE: Dict[str, Any] = {
    "category_key": "unknown",
    "display_name": "Неопределённая категория",
    "definition": "Тип средства не определён по доверенным данным каталога.",
    "intended_purpose": "Не установлено.",
    "typical_functions": ["не установлены"],
    "analysis_criteria": ["только подтверждённые данные состава и профиля"],
    "relevant_ingredient_classes": ["без предположений"],
    "profile_considerations": ["соответствие подтверждённым факторам"],
    "limitations": [
        "не приписывать продукту функцию только по названию",
        "не делать выводов о категории без доверенных данных",
    ],
    "common_mistakes": [
        "приписывание увлажнения/питания/восстановления без оснований",
    ],
    "report_guidance": (
        "Опираться только на подтверждённые факторы и состав; не утверждать "
        "функциональные свойства, которые не подтверждены."
    ),
    "version": CATEGORY_KNOWLEDGE_VERSION,
}


def get_category_knowledge(product_type: str) -> Dict[str, Any]:
    """Возвращает запись знаний по каноническому названию категории (title).

    Категория определяется по доверенной таксономии каталога, а не по
    свободному тексту клиента. Для неизвестной категории — fallback.
    """
    from .catalog_taxonomy import subcategory_key_for_title

    if not product_type:
        return FALLBACK_CATEGORY_KNOWLEDGE
    hit = subcategory_key_for_title(product_type)
    if not hit:
        return FALLBACK_CATEGORY_KNOWLEDGE
    body_area, key = hit
    return CATEGORY_KNOWLEDGE.get(f"{body_area}:{key}", FALLBACK_CATEGORY_KNOWLEDGE)


def render_category_knowledge(product_type: str) -> str:
    """Рендерит запись знаний в короткий текст для LLM-контекста."""
    k = get_category_knowledge(product_type)
    lines: list[str] = []
    if k.get("display_name"):
        lines.append(f"Категория: {k['display_name']}")
    if k.get("definition"):
        lines.append(f"Что это: {k['definition']}")
    if k.get("intended_purpose"):
        lines.append(f"Назначение: {k['intended_purpose']}")
    funcs = k.get("typical_functions") or []
    if funcs:
        lines.append("Типичные функции: " + "; ".join(funcs))
    crit = k.get("analysis_criteria") or []
    if crit:
        lines.append("Что уместно анализировать: " + "; ".join(crit))
    lim = k.get("limitations") or []
    if lim:
        lines.append("Нельзя автоматически заключать: " + "; ".join(lim))
    err = k.get("common_mistakes") or []
    if err:
        lines.append("Избегать неподтверждённых утверждений: " + "; ".join(err))
    if k.get("report_guidance"):
        lines.append(f"Как объяснять результат: {k['report_guidance']}")
    return "\n".join(lines)


CATEGORY_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "face:cleansing": {
        "category_key": "face:cleansing",
        "display_name": "Очищение и демакияж",
        "definition": "Средство для удаления декоративной косметики, солнцезащитных продуктов и/или загрязнений в пределах назначения конкретного продукта.",
        "intended_purpose": "Очистить кожу и/или снять макияж; обычно смывается водой.",
        "typical_functions": ["очищение", "снятие макияжа", "удаление загрязнений"],
        "analysis_criteria": ["очищающие компоненты", "общие свойства формулы", "особенности снятия макияжа", "потенциальная раздражающая нагрузка", "соответствие профилю"],
        "relevant_ingredient_classes": ["сурфактанты", "эмульгаторы", "солюбилизаторы", "успокаивающие компоненты"],
        "profile_considerations": ["риск раздражения и пересушивания", "чувствительность кожи", "необходимость смывания"],
        "limitations": ["не питает кожу", "не даёт интенсивного увлажнения", "не восстанавливает барьер", "не обязательно снимает любой стойкий макияж"],
        "common_mistakes": ["называть очищение питающим/увлажняющим", "обещать снятие любого стойкого макияжа"],
        "report_guidance": "Описывать очищающую функцию и раздражающую нагрузку; не приписывать уходовые эффекты без подтверждённых факторов.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:toning": {
        "category_key": "face:toning",
        "display_name": "Тонизирование",
        "definition": "Тоник/тонер, применяемый после очищения для подготовки кожи и/или лёгкого увлажнения.",
        "intended_purpose": "Освежить/подготовить кожу после очищения; обычно не смывается.",
        "typical_functions": ["тонизирование", "лёгкое увлажнение", "подготовка к дальнейшему уходу"],
        "analysis_criteria": ["состав", "успокаивающие или активные компоненты", "потенциальное раздражение"],
        "relevant_ingredient_classes": ["хумектанты", "успокаивающие", "кислоты (при наличии)"],
        "profile_considerations": ["чувствительность", "переносимость спирта/кислот"],
        "limitations": ["не является полноценным увлажняющим кремом", "не обязательно содержит активы в значимой концентрации"],
        "common_mistakes": ["описывать тонер как сыворотку/крем", "обещать глубокое увлажнение"],
        "report_guidance": "Описывать роль тонера и подтверждённые свойства состава, без завышения до полноценного ухода.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:serums": {
        "category_key": "face:serums",
        "display_name": "Сыворотки",
        "definition": "Концентрированное средство с целевыми активными компонентами, наносимое на очищенную кожу.",
        "intended_purpose": "Доставить целевые активы (увлажнение, осветление, антивозраст и т.п.).",
        "typical_functions": ["целевое действие активов", "высокая концентрация активов"],
        "analysis_criteria": ["фактическое назначение", "состав", "подтверждённые свойства активов"],
        "relevant_ingredient_classes": ["активы по назначению", "хумектанты", "антиоксиданты"],
        "profile_considerations": ["переносимость активов", "чувствительность", "сочетаемость с терапией"],
        "limitations": ["наличие одного ингредиента не гарантирует эффект", "маркетинговое название не равно действию"],
        "common_mistakes": ["приписывать эффект только по маркетинговому названию", "называть концентрацию без данных"],
        "report_guidance": "Связывать выводы с подтверждёнными свойствами активов, а не с названием продукта.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:creams": {
        "category_key": "face:creams",
        "display_name": "Кремы",
        "definition": "Эмульсионное средство с увлажняющей/смягчающей основой для нанесения на кожу.",
        "intended_purpose": "Увлажнить/смягчить кожу, создать защитный слой в зависимости от состава.",
        "typical_functions": ["увлажнение", "смягчение", "поддержка барьера (при подтверждении)"],
        "analysis_criteria": ["подтверждённые увлажняющие и смягчающие компоненты", "поддержка барьера", "соответствие профилю"],
        "relevant_ingredient_classes": ["хумектанты", "эмоленты", "окклюзивы", "церамиды"],
        "profile_considerations": ["тип кожи", "склонность к закупорке пор", "чувствительность"],
        "limitations": ["название «крем» не доказывает интенсивное увлажнение или восстановление барьера"],
        "common_mistakes": ["называть любой крем восстанавливающим барьер", "обещать интенсивное питание без состава"],
        "report_guidance": "Опираться на подтверждённые увлажняющие/смягчающие свойства ингредиентов.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:moisturizing": {
        "category_key": "face:moisturizing",
        "display_name": "Увлажнение и питание",
        "definition": "Средство, направленное на увлажнение и/или питание кожи.",
        "intended_purpose": "Увлажнить и/или напитать кожу.",
        "typical_functions": ["увлажнение", "питание"],
        "analysis_criteria": ["подтверждённые увлажняющие компоненты", "смягчающие свойства", "поддержка барьера"],
        "relevant_ingredient_classes": ["хумектанты", "эмоленты", "церамиды", "масла"],
        "profile_considerations": ["тип кожи", "обезвоженность", "склонность к закупорке пор"],
        "limitations": ["не всякое «увлажнение» подтверждено составом", "не доказывать восстановление барьера без оснований"],
        "common_mistakes": ["обещать глубокое увлажнение по названию", "приписывать барьер-восстановление"],
        "report_guidance": "Связывать увлажнение с подтверждёнными хумектантами/эмолентами.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:scrubs": {
        "category_key": "face:scrubs",
        "display_name": "Скрабы и пилинги",
        "definition": "Эксфолиант (механический скраб или химический пилинг), удаляющий ороговевшие клетки.",
        "intended_purpose": "Отшелушивание/обновление кожи.",
        "typical_functions": ["отшелушивание", "обновление поверхности кожи"],
        "analysis_criteria": ["подтверждённые отшелушивающие компоненты", "назначение", "раздражающая нагрузка", "соответствие профилю"],
        "relevant_ingredient_classes": ["AHA/BHA/PHA кислоты", "абразивные частицы", "ферменты"],
        "profile_considerations": ["чувствительность", "переносимость кислот", "активная терапия"],
        "limitations": ["не делать вывод о концентрации, силе или pH без данных"],
        "common_mistakes": ["называть концентрацию/силу отшелушивания без данных", "обещать безопасность для чувствительной кожи"],
        "report_guidance": "Учитывать отшелушивающие компоненты и раздражающую нагрузку, без домыслов о концентрации.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:masks": {
        "category_key": "face:masks",
        "display_name": "Маски",
        "definition": "Средство, наносимое на ограниченное время (тканевая, смываемая, ночная, глиняная, патч-маска).",
        "intended_purpose": "Временное интенсивное воздействие в зависимости от типа маски.",
        "typical_functions": ["увлажнение", "очищение", "успокоение", "отшелушивание — в зависимости от типа"],
        "analysis_criteria": ["тип маски", "состав", "подтверждённые свойства компонентов"],
        "relevant_ingredient_classes": ["увлажнители", "глина", "кислоты", "успокаивающие"],
        "profile_considerations": ["чувствительность", "время воздействия", "переносимость"],
        "limitations": ["не давать универсальную инструкцию без знания типа маски"],
        "common_mistakes": ["приписывать эффект без учёта типа маски", "обещать долгосрочный результат"],
        "report_guidance": "Учитывать тип маски и подтверждённые свойства; не обещать стойкий эффект.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:patches": {
        "category_key": "face:patches",
        "display_name": "Патчи",
        "definition": "Пластыри/накладки, наклеиваемые локально на нужную область.",
        "intended_purpose": "Локальное воздействие на конкретную зону (под глаза, на несовершенства).",
        "typical_functions": ["локальное увлажнение/успокоение"],
        "analysis_criteria": ["состав", "назначение зоны"],
        "relevant_ingredient_classes": ["увлажнители", "успокаивающие"],
        "profile_considerations": ["чувствительность зоны", "переносимость"],
        "limitations": ["не наносятся ровным слоем", "не заменяют полноценный уход"],
        "common_mistakes": ["описывать как крем/сыворотку"],
        "report_guidance": "Описывать локальное применение и подтверждённые свойства.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:pads": {
        "category_key": "face:pads",
        "display_name": "Пэды",
        "definition": "Пропитанные диски/подушечки для протирания кожи.",
        "intended_purpose": "Нанесение средства протиранием (часто с эксфолиантом или тоником).",
        "typical_functions": ["нанесение активов", "лёгкое отшелушивание"],
        "analysis_criteria": ["состав пропитки", "наличие кислот/активов"],
        "relevant_ingredient_classes": ["кислоты", "увлажнители", "успокаивающие"],
        "profile_considerations": ["чувствительность", "переносимость"],
        "limitations": ["не доказывать концентрацию/силу без данных"],
        "common_mistakes": ["приписывать глубину действия без состава"],
        "report_guidance": "Описывать состав пропитки и подтверждённые свойства.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:eyes": {
        "category_key": "face:eyes",
        "display_name": "Для кожи вокруг глаз",
        "definition": "Уход, предназначенный для тонкой кожи вокруг глаз.",
        "intended_purpose": "Уход за областью вокруг глаз (увлажнение, уменьшение отёчности — при подтверждении).",
        "typical_functions": ["увлажнение области вокруг глаз"],
        "analysis_criteria": ["состав", "подтверждённые увлажняющие/успокаивающие компоненты"],
        "relevant_ingredient_classes": ["хумектанты", "пептиды", "успокаивающие"],
        "profile_considerations": ["чувствительность зоны", "отёчность/тёмные круги (только при подтверждении)"],
        "limitations": ["не обещать устранение тёмных кругов или отёков без подтверждённых данных"],
        "common_mistakes": ["обещать убрать тёмные круги", "называть лифтинг без состава"],
        "report_guidance": "Описывать подтверждённые свойства, без обещаний устранения тёмных кругов.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:lips": {
        "category_key": "face:lips",
        "display_name": "Уход для губ",
        "definition": "Средство для ухода за кожей губ.",
        "intended_purpose": "Увлажнение/защита губ.",
        "typical_functions": ["увлажнение губ", "смягчение"],
        "analysis_criteria": ["состав", "увлажняющие/смягчающие компоненты"],
        "relevant_ingredient_classes": ["эмоленты", "окклюзивы", "хумектанты"],
        "profile_considerations": ["сухость губ", "чувствительность"],
        "limitations": ["не приписывать лечебное действие"],
        "common_mistakes": ["обещать заживление/лечение"],
        "report_guidance": "Описывать увлажняющие свойства состава.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:special": {
        "category_key": "face:special",
        "display_name": "Специальный уход",
        "definition": "Точечные/специализированные средства (точечные от акне, бустеры, концентраты).",
        "intended_purpose": "Целевое воздействие на конкретную проблему.",
        "typical_functions": ["целевое действие", "локальное применение"],
        "analysis_criteria": ["состав", "подтверждённые свойства активов", "назначение"],
        "relevant_ingredient_classes": ["точечные активы (салициловая кислота, сера и т.п.)"],
        "profile_considerations": ["переносимость", "чувствительность", "сочетаемость"],
        "limitations": ["не обещать лечение акне/проблемы без подтверждения"],
        "common_mistakes": ["обещать лечение", "приписывать эффект без данных"],
        "report_guidance": "Описывать подтверждённые свойства активов, без лечебных обещаний.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "face:antiage": {
        "category_key": "face:antiage",
        "display_name": "Антивозрастной уход",
        "definition": "Средство, позиционируемое для уменьшения признаков старения.",
        "intended_purpose": "Снижение выраженности признаков старения (при подтверждении).",
        "typical_functions": ["антивозрастное действие", "поддержка упругости (при подтверждении)"],
        "analysis_criteria": ["состав", "подтверждённые антивозрастные активы (ретиноиды, пептиды, антиоксиданты)"],
        "relevant_ingredient_classes": ["ретиноиды", "пептиды", "антиоксиданты"],
        "profile_considerations": ["переносимость ретиноидов", "чувствительность", "возраст"],
        "limitations": ["не обещать разглаживание морщин без данных", "не называть концентрацию ретиноида без состава"],
        "common_mistakes": ["обещать омоложение", "приписывать эффект по названию «anti-age»"],
        "report_guidance": "Опираться на подтверждённые антивозрастные активы, без обещаний.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:foundation": {
        "category_key": "makeup:foundation",
        "display_name": "Тональные средства",
        "definition": "Декоративное средство, выравнивающее тон кожи лица.",
        "intended_purpose": "Выравнивание тона, маскировка несовершенств.",
        "typical_functions": ["выравнивание тона", "покрытие"],
        "analysis_criteria": ["тип формулы", "пигменты", "потенциально раздражающие компоненты", "соответствие профилю"],
        "relevant_ingredient_classes": ["пигменты", "силиконы", "спирты (при наличии)"],
        "profile_considerations": ["чувствительность", "склонность к акне", "переносимость"],
        "limitations": ["не восстанавливает барьер", "не питает/не лечит кожу без подтверждённых оснований"],
        "common_mistakes": ["описывать декоративный продукт как уходовый/лечащий"],
        "report_guidance": "Описывать декоративное назначение и потенциальные риски для профиля, без уходовых обещаний.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:concealers": {
        "category_key": "makeup:concealers",
        "display_name": "Консилеры",
        "definition": "Декоративное средство для точечной маскировки несовершенств.",
        "intended_purpose": "Точечная маскировка.",
        "typical_functions": ["маскировка"],
        "analysis_criteria": ["тип формулы", "пигменты", "потенциальные риски"],
        "relevant_ingredient_classes": ["пигменты", "силиконы"],
        "profile_considerations": ["чувствительность", "склонность к акне"],
        "limitations": ["не лечит несовершенства"],
        "common_mistakes": ["обещать лечебное действие"],
        "report_guidance": "Описывать маскирующее назначение, без лечебных обещаний.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:powders": {
        "category_key": "makeup:powders",
        "display_name": "Пудры",
        "definition": "Порошковое декоративное средство для матирования/фиксации.",
        "intended_purpose": "Матирование, фиксация макияжа.",
        "typical_functions": ["матирование", "фиксация"],
        "analysis_criteria": ["состав", "абсорбирующие компоненты", "потенциальные риски"],
        "relevant_ingredient_classes": ["абсорбенты", "пигменты", "тальк/минералы"],
        "profile_considerations": ["жирность кожи", "чувствительность"],
        "limitations": ["не лечит акне/жирность"],
        "common_mistakes": ["обещать лечение акне"],
        "report_guidance": "Описывать матирующее назначение.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:blush": {
        "category_key": "makeup:blush",
        "display_name": "Румяна",
        "definition": "Декоративное средство для придания цвета щекам.",
        "intended_purpose": "Придание цвета.",
        "typical_functions": ["придание цвета"],
        "analysis_criteria": ["состав", "пигменты", "потенциальные риски"],
        "relevant_ingredient_classes": ["пигменты"],
        "profile_considerations": ["чувствительность"],
        "limitations": ["не уходовое средство"],
        "common_mistakes": ["описывать как уход"],
        "report_guidance": "Описывать декоративное назначение.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:mascara": {
        "category_key": "makeup:mascara",
        "display_name": "Тушь",
        "definition": "Декоративное средство для ресниц.",
        "intended_purpose": "Придание объёма/длины ресницам.",
        "typical_functions": ["объём/длина ресниц"],
        "analysis_criteria": ["состав", "потенциальные раздражители (для глаз)"],
        "relevant_ingredient_classes": ["пигменты", "воски", "консерванты"],
        "profile_considerations": ["чувствительность глаз"],
        "limitations": ["не ухаживает за ресницами без подтверждения"],
        "common_mistakes": ["обещать рост ресниц"],
        "report_guidance": "Описывать декоративное назначение и раздражающий потенциал.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:lipstick": {
        "category_key": "makeup:lipstick",
        "display_name": "Помады",
        "definition": "Декоративное средство для губ.",
        "intended_purpose": "Придание цвета губам.",
        "typical_functions": ["цвет губ"],
        "analysis_criteria": ["состав", "пигменты", "потенциальные раздражители"],
        "relevant_ingredient_classes": ["пигменты", "воски", "масла"],
        "profile_considerations": ["чувствительность губ"],
        "limitations": ["не лечит губы"],
        "common_mistakes": ["обещать увлажнение/лечение без состава"],
        "report_guidance": "Описывать декоративное назначение.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
    "makeup:eyes": {
        "category_key": "makeup:eyes",
        "display_name": "Макияж для глаз",
        "definition": "Декоративное средство для области вокруг глаз (тени, подводка).",
        "intended_purpose": "Макияж глаз.",
        "typical_functions": ["макияж глаз"],
        "analysis_criteria": ["состав", "пигменты", "потенциальные раздражители"],
        "relevant_ingredient_classes": ["пигменты", "консерванты"],
        "profile_considerations": ["чувствительность глаз"],
        "limitations": ["не ухаживает за кожей вокруг глаз"],
        "common_mistakes": ["описывать как уход для век"],
        "report_guidance": "Описывать декоративное назначение и раздражающий потенциал.",
        "version": CATEGORY_KNOWLEDGE_VERSION,
    },
}
