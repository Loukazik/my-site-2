import os
import pymysql
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

# Импортируем официальный клиент для работы с ИИ
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "1581"

def connect():
    return mysql.connector.connect(
        host="185.114.247.43",
        port=3306,
        database="sch688_vvedenie",
        user="sch688_vvedenie",
        password="Qwerty123"
    )

# =========================================================================
# 2. НАСТРОЙКИ ИИ (DEEPSEEK / OPENAI COMPATIBLE)
# =========================================================================
# Замените 'your_real_api_key_here' на ваш ключ от кабинета DeepSeek (или OpenAI)
DEEPSEEK_API_KEY = "your_real_api_key_here" 

# Инициализируем клиент. Для DeepSeek указывается их базовый URL
ai_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    email VARCHAR(150) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    balance DOUBLE DEFAULT 100.0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_chat (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    message TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            ''')
        conn.commit()
    finally:
        conn.close()

init_db()

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
                user = cursor.fetchone()
        finally:
            conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный Email или пароль.', 'error')
            return render_template('login.html')
            
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        flash('Пожалуйста, сначала войдите в аккаунт.', 'error')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT balance FROM users WHERE id = %s', (user_id,))
            user_data = cursor.fetchone()
            current_balance = user_data['balance'] if user_data else 0.0

            if request.method == 'POST':
                user_message = request.form.get('message')
                
                if user_message and user_message.strip():
                    COST = 5.0
                    if current_balance < COST:
                        flash('Недостаточно баланса для запроса к ИИ!', 'error')
                    else:
                        # 1. Сохраняем сообщение пользователя в базу данных
                        cursor.execute(
                            'INSERT INTO ai_chat (user_id, role, message) VALUES (%s, %s, %s)', 
                            (user_id, 'user', user_message)
                        )
                        
                        # 2. Списываем баланс за генерацию
                        new_balance = current_balance - COST
                        cursor.execute('UPDATE users SET balance = %s WHERE id = %s', (new_balance, user_id))
                        conn.commit()
                        current_balance = new_balance

                        # 3. ЗАПРОС К НАСТОЯЩЕЙ НЕЙРОСЕТИ
                        try:
                            # Отправляем запрос в DeepSeek API
                            completion = ai_client.chat.completions.create(
                                model="deepseek-chat",  # Имя модели в системе DeepSeek
                                messages=[
                                    {"role": "system", "content": "Ты дружелюбный и полезный ИИ-ассистент на сайте пользователя."},
                                    {"role": "user", "content": user_message}
                                ],
                                timeout=45  # Ограничение времени ожидания ответа (в секундах)
                            )
                            # Извлекаем текст ответа нейросети
                            ai_response = completion.choices[0].message.content
                        except Exception as e:
                            # Резервный ответ на случай падения сети/окончания денег на балансе API
                            ai_response = f"Извините, сервер ИИ сейчас перегружен или недоступен. (Ошибка: {str(e)})"

                        # 4. Сохраняем ответ ИИ в базу данных
                        cursor.execute(
                            'INSERT INTO ai_chat (user_id, role, message) VALUES (%s, %s, %s)', 
                            (user_id, 'ai', ai_response)
                        )
                        conn.commit()

            cursor.execute('SELECT role, message FROM ai_chat WHERE user_id = %s ORDER BY id ASC', (user_id,))
            chat_history = cursor.fetchall()
            
    finally:
        conn.close()
        
    return render_template('dashboard.html', username=session['username'], balance=current_balance, chat_history=chat_history)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы.', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm-password')
        
        if password != confirm_password:
            flash('Ошибка: Пароли не совпадают!', 'error')
            return render_template('register.html')
            
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    flash('Ошибка: Пользователь с таким Email уже зарегистрирован!', 'error')
                    return render_template('register.html')
                    
                hashed_password = generate_password_hash(password)
                
                cursor.execute(
                    'INSERT INTO users (username, email, password, balance) VALUES (%s, %s, %s, %s)',
                    (username, email, hashed_password, 100.0)
                )
                conn.commit()
                flash(f'Успех! Аккаунт {username} создан. Теперь вы можете войти.', 'success')
                return redirect(url_for('login'))
                
        except pymysql.MySQLError as e:
            flash(f'Произошла ошибка базы данных: {e}', 'error')
        finally:
            conn.close()
        
    return render_template('register.html')

if __name__ == '__main__':
    app.run(debug=True)