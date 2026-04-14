from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import os
import database
from werkzeug.utils import secure_filename
import pandas as pd
from datetime import datetime, timedelta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = 'your_secret_key_here' # Replace with a real secret key
app.permanent_session_lifetime = timedelta(minutes=30)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_actual_remote_address():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return get_remote_address()

limiter = Limiter(
    key_func=get_actual_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    emp_id = session['user_id']
    
    if request.method == 'POST':
        data = {
            'gender': request.form.get('gender'),
            'top_size': request.form.get('top_size'),
            'top_color': request.form.get('top_color'),
            'bottom_size': request.form.get('bottom_size'),
            'bottom_color': request.form.get('bottom_color')
        }
        database.update_employee_info(emp_id, data)
        flash('의류 옵션이 성공적으로 저장되었습니다.', 'success')
        # Redirect to dashboard to render the updated state
        return redirect(url_for('dashboard'))
        
    conn = database.get_db_connection()
    user_row = conn.execute('SELECT * FROM employees WHERE emp_id = ?', (emp_id,)).fetchone()
    conn.close()
    
    if not user_row:
        session.clear()
        flash('사용자 정보를 찾을 수 없어 로그아웃되었습니다.', 'error')
        return redirect(url_for('index'))
        
    user = dict(user_row)
    return render_template('dashboard.html', user=user, name=session['user_name'])

# Initialize DB on start
database.init_db()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/proposal')
def view_proposal():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    filepath = os.path.join(basedir, '2-1. 노사협력선언 26주년 기념품 제안서(임직원용)_트레이닝복 상하의세트.pdf')
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='application/pdf')
    else:
        flash('의류 제안서 파일을 찾을 수 없습니다.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/login', methods=['POST'])
def login():
    emp_id = request.form.get('emp_id')

    user = database.get_employee_by_auth(emp_id)
    
    if user:
        session['user_id'] = user['emp_id']
        session['user_name'] = user['name']
        return redirect(url_for('dashboard'))
    else:
        flash('사번이 올바르지 않거나 등록되지 않았습니다.', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))



@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        real_password = database.get_setting('admin_password', 'admin1234')
        
        if password == real_password:
            session['is_admin'] = True
            return redirect(url_for('admin'))
        else:
            flash('비밀번호가 올바르지 않습니다.', 'error')
            return redirect(url_for('admin_login'))
            
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET'])
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    last_upload_time = database.get_setting('last_upload_time', '-')
    
    return render_template('admin.html', 
                         last_upload_time=last_upload_time)

@app.route('/admin/settings', methods=['POST'])
def update_settings():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    new_password = request.form.get('new_password')
    if new_password:
        database.set_setting('admin_password', new_password)
        flash('비밀번호가 변경되었습니다.', 'success')
    else:
        flash('변경된 설정이 없습니다.', 'info')

    return redirect(url_for('admin'))

@app.route('/admin/upload', methods=['POST'])
def upload_excel():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    if 'file' not in request.files:
        flash('파일이 없습니다.', 'error')
        return redirect(url_for('admin'))
    
    file = request.files['file']
    if file.filename == '':
        flash('선택된 파일이 없습니다.', 'error')
        return redirect(url_for('admin'))
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            count = database.upsert_employees_from_excel(filepath)
            flash(f'{count}명의 사원 정보가 업데이트되었습니다.', 'success')
        except Exception as e:
            flash(f'오류 발생: {str(e)}', 'error')
            
    return redirect(url_for('admin'))

@app.route('/admin/download')
def download_excel():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    df = database.get_all_employees()
    
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'employees_updated_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx')
    df.to_excel(output_path, index=False)
    
    return send_file(output_path, as_attachment=True)

@app.route('/admin/reset', methods=['POST'])
@limiter.limit("3 per minute")
def admin_reset():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    password = request.form.get('password')
    current_admin_pw = database.get_setting('admin_password', 'admin1234')
    
    if password == current_admin_pw:
        database.reset_all_data()
        flash('모든 데이터가 초기화되었습니다.', 'success')
    else:
        flash('비밀번호가 일치하지 않아 초기화에 실패했습니다.', 'danger')
        
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
