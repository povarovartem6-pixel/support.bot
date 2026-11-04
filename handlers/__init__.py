from aiogram import Dispatcher

from handlers import user, admin


def register_handlers(dp: Dispatcher):
    dp.include_router(user.router)
    dp.include_router(admin.router)
