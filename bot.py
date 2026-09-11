import logging
from telegram import Update
from telegram.ext import Application
import config,database
from handlers import register

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s: %(message)s')

def main():
    database.init_db()
    app=Application.builder().token(config.BOT_TOKEN).build()
    register(app)
    app.run_polling(allowed_updates=['message','edited_message','callback_query','chat_member','chat_join_request','my_chat_member'],drop_pending_updates=True)
if __name__=='__main__':main()
