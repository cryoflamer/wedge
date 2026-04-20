from __future__ import annotations

from PySide6.QtWidgets import QWidget


TOOLTIPS: dict[str, str] = {
    "phase_panel_wall_1": "Фазовий портрет для стартів зі стінки 1. Лівий клік додає траєкторію.",
    "phase_panel_wall_2": "Фазовий портрет для стартів зі стінки 2. Лівий клік додає траєкторію.",
    "wedge_panel": "Геометричний вигляд клина з параболічними сегментами та точками відбиття.",
    "angle_panel": "Простір параметрів alpha і beta. Клік змінює кути системи.",
    "status_label": "Поточний стан фонового job або replay.",
    "status_job_button_cancel": "Зупинити поточний фоновий job.",
    "status_job_button_resume": "Продовжити вибраний призупинений job.",
    "status_jobs_selector": "Вибір призупиненого job для відновлення.",
    "status_progress": "Прогрес поточного фонового job.",
    "status_fast_build": "Швидкий режим: оновлювати UI рідше, щоб прискорити побудову.",
    "selected_trajectory": "Вибір активної траєкторії для replay, аналізу і дій зі списку.",
    "toggle_visibility": "Перемкнути видимість вибраної траєкторії на всіх панелях.",
    "clear_selected": "Видалити вибрану траєкторію.",
    "add_seed_shortcut": "Відкрити секцію ручного додавання нової траєкторії.",
    "compute_lyapunov": "Обчислити finite-time показник Ляпунова для вибраної траєкторії.",
    "clear_all": "Видалити всі траєкторії та пов'язані паузені job-и.",
    "trajectory_summary": "Коротка інформація про вибрану траєкторію.",
    "angle_units": "Одиниці відображення кутів у полях alpha і beta.",
    "alpha_edit": "Кут alpha. Підтримуються десятковий запис і вирази через pi.",
    "beta_edit": "Кут beta. Підтримуються десятковий запис і вирази через pi.",
    "n_phase_edit": "Кількість фазових ітерацій для кожної траєкторії.",
    "n_geom_edit": "Кількість геометричних відбиттів, які показуються в клині.",
    "symmetric_mode": "Автоматично тримати beta на симетричній межі pi - alpha.",
    "fixed_domain": "Фіксований фазовий домен. Вимкніть, щоб дозволити zoom і pan.",
    "show_regions": "Показати області на діаграмі alpha/beta.",
    "show_region_labels": "Показати текстові мітки областей на діаграмі alpha/beta.",
    "show_region_legend": "Показати легенду областей на діаграмі alpha/beta.",
    "show_branch_markers": "Показати службові позначки гілок на фазових панелях.",
    "show_heatmap": "Увімкнути теплову карту розподілу точок на фазових панелях.",
    "heatmap_mode": "Режим побудови heatmap: для всіх або лише для вибраної траєкторії.",
    "heatmap_bins": "Кількість бінів heatmap по кожній осі.",
    "heatmap_norm": "Нормалізація heatmap: лінійна або логарифмічна.",
    "apply": "Перебудувати всі траєкторії для поточних параметрів.",
    "reset_phase_view": "Скинути zoom і pan фазових панелей.",
    "replay_selected": "Покроково програти тільки вибрану траєкторію.",
    "replay_all": "Покроково програти всі видимі траєкторії.",
    "pause": "Поставити replay на паузу.",
    "resume": "Продовжити replay після паузи.",
    "step": "Виконати один крок replay.",
    "reset_replay": "Скинути replay на початок.",
    "manual_d": "Початкове значення d для ручного додавання траєкторії.",
    "manual_tau": "Початкове значення tau для ручного додавання траєкторії.",
    "manual_wall": "Стартова стінка для ручно доданої траєкторії.",
    "add_trajectory": "Додати нову траєкторію з введених вручну d, tau і wall.",
    "scan_mode": "Тип scan-генерації стартових точок.",
    "scan_wall": "Стінка, для якої створюються seed-и під час scan.",
    "scan_count": "Кількість seed-ів, які треба згенерувати в scan.",
    "scan_d_min": "Нижня межа d для scan.",
    "scan_d_max": "Верхня межа d для scan.",
    "scan_tau_min": "Нижня межа tau для scan.",
    "scan_tau_max": "Верхня межа tau для scan.",
    "run_scan": "Запустити масове додавання траєкторій у фоновому job.",
    "export_mode": "Режим експорту зображення: кольоровий або монохромний.",
    "mono_preset": "Стиль ліній для монохромного PNG-експорту.",
    "data_export_format": "Формат експорту даних траєкторій.",
    "export_data": "Експортувати дані траєкторій у файл.",
    "export_png": "Експортувати поточні панелі у PNG.",
    "save_session": "Зберегти поточну сесію у файл.",
    "load_session": "Завантажити сесію з файла.",
}


def tooltip_text(key: str) -> str:
    return TOOLTIPS[key]


def apply_tooltip(widget: QWidget, key: str) -> None:
    text = tooltip_text(key)
    widget.setToolTip(text)
    widget.setStatusTip(text)
