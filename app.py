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
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['GIFT_IMAGE_FOLDER'] = 'uploads/gift_images/'
os.makedirs(app.config['GIFT_IMAGE_FOLDER'], exist_ok=True)

# V10: Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ... (Previous code remains same until gift_update route)

@app.route('/gift_update', methods=['GET', 'POST'])
def gift_update():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if database.get_setting('enable_gift_update', 'true') != 'true':
        flash('현재 이 기능은 비활성화되어 있습니다.', 'error')
        return redirect(url_for('dashboard'))
    
    emp_id = session['user_id']
    
    if request.method == 'POST':
        data = {
            'gift_address': request.form.get('gift_address'),
            'gift_address_detail': request.form.get('gift_address_detail'),
            'gift_zipcode': request.form.get('gift_zipcode'),
            'gift_receiver': request.form.get('gift_receiver'),
            'selected_gift_id': request.form.get('selected_gift_id') # V13
        }
        database.update_employee_info(emp_id, data)
        flash('선물 배송지 정보가 저장되었습니다.', 'success')
        return redirect(url_for('dashboard'))
    
    conn = database.get_db_connection()
    user_row = conn.execute('SELECT * FROM employees WHERE emp_id = ?', (emp_id,)).fetchone()
    conn.close()
    
    gift_options = database.get_gift_options() # V13
    
    if user_row:
        user = dict(user_row)
        # V9: Default to Info Address if Gift Address is empty
        if not user.get('gift_address'):
            user['gift_address'] = user.get('address_main')
            user['gift_address_detail'] = user.get('address_main_detail')
            user['gift_zipcode'] = user.get('zipcode')
            user['gift_receiver'] = user.get('name')
    else:
        return redirect(url_for('index'))
    
    return render_template('gift_update.html', user=user, gift_options=gift_options)

# ... (Previous code remains same until admin routes)

@app.route('/admin/gifts', methods=['GET'])
def admin_gifts():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    gifts = database.get_gift_options()
    return render_template('admin_gifts.html', gifts=gifts)

@app.route('/admin/gifts/add', methods=['POST'])
def admin_add_gift():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    file = request.files.get('image')
    
    image_path = ''
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['GIFT_IMAGE_FOLDER'], filename)
        file.save(filepath)
        # Store relative path for serving
        image_path = f"uploads/gift_images/{filename}"
        
    database.add_gift_option(name, description, image_path)
    flash('선물이 추가되었습니다.', 'success')
    return redirect(url_for('admin_gifts'))

@app.route('/admin/gifts/delete/<int:gift_id>', methods=['POST'])
def admin_delete_gift(gift_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    database.delete_gift_option(gift_id)
    flash('선물이 삭제되었습니다.', 'success')
    return redirect(url_for('admin_gifts'))

# Serve uploaded files (for gift images)
@app.route('/uploads/gift_images/<filename>')
def uploaded_gift_image(filename):
    return send_file(os.path.join(app.config['GIFT_IMAGE_FOLDER'], filename))


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize DB on start
database.init_db()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    emp_id = request.form.get('emp_id')
    ssn_last = request.form.get('ssn_last')
    agree_privacy = request.form.get('agree_privacy')

    user = database.get_employee_by_auth(emp_id, ssn_last)
    
    if user:
        if not agree_privacy:
            flash('개인정보 수집 및 이용에 동의해야 합니다.', 'error')
            return redirect(url_for('index'))
            
        # Record consent
        database.update_privacy_consent(user['emp_id'])
        
        session['user_id'] = user['emp_id']
        session['user_name'] = user['name']
        return redirect(url_for('dashboard'))
    else:
        flash('사번 또는 주민등록번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    enable_info = database.get_setting('enable_info_update', 'true') == 'true'
    enable_gift = database.get_setting('enable_gift_update', 'true') == 'true'
    
    return render_template('dashboard.html', 
                         name=session['user_name'],
                         enable_info=enable_info,
                         enable_gift=enable_gift)

@app.route('/info_update', methods=['GET', 'POST'])
def info_update():
    if 'user_id' not in session:
        return redirect(url_for('index'))
        
    if database.get_setting('enable_info_update', 'true') != 'true':
        flash('현재 이 기능은 비활성화되어 있습니다.', 'error')
        return redirect(url_for('dashboard'))
    
    emp_id = session['user_id']
    
    if request.method == 'POST':
        data = {
            'address_main': request.form.get('address_main'),
            'address_main_detail': request.form.get('address_main_detail'),
            'zipcode': request.form.get('zipcode'),
            'phone': request.form.get('phone')
        }
        database.update_employee_info(emp_id, data)
        flash('인사 정보가 수정되었습니다.', 'success')
        return redirect(url_for('dashboard'))
    
    conn = database.get_db_connection()
    user = conn.execute('SELECT * FROM employees WHERE emp_id = ?', (emp_id,)).fetchone()
    conn.close()
    
    return render_template('info_update.html', user=user)



@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute") # V10: Rate Limit Admin Login
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
        
    enable_info = database.get_setting('enable_info_update', 'true') == 'true'
    enable_gift = database.get_setting('enable_gift_update', 'true') == 'true'
    last_upload_time = database.get_setting('last_upload_time', '-')
    
    return render_template('admin.html', 
                         enable_info=enable_info, 
                         enable_gift=enable_gift,
                         last_upload_time=last_upload_time)

@app.route('/admin/settings', methods=['POST'])
def update_settings():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    enable_info = 'true' if request.form.get('enable_info') else 'false'
    enable_gift = 'true' if request.form.get('enable_gift') else 'false'
    
    database.set_setting('enable_info_update', enable_info)
    database.set_setting('enable_gift_update', enable_gift)
    
    # Password Change
    new_password = request.form.get('new_password')
    if new_password:
        database.set_setting('admin_password', new_password)
        flash('비밀번호 및 설정이 저장되었습니다.', 'success')
    else:
        flash('시스템 설정이 저장되었습니다.', 'success')

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
    
    # Export to Excel
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'employees_updated_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx')
    df.to_excel(output_path, index=False)
    
    return send_file(output_path, as_attachment=True)



@app.route('/admin/reset', methods=['POST'])
@limiter.limit("3 per minute") # Rate limit specifically for sensitive action
def admin_reset():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    password = request.form.get('password')
    # Use same logic as login
    current_admin_pw = database.get_setting('admin_password', 'admin1234')
    
    if password == current_admin_pw:
        database.reset_all_data()
        flash('모든 데이터가 초기화되었습니다.', 'success')
    else:
        flash('비밀번호가 일치하지 않아 초기화에 실패했습니다.', 'danger')
        
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
