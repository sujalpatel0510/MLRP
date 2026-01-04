# ======================== IMPORTS ========================
from sqlalchemy import text
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import send_file
import os

# ======================== NEW IMPORTS FOR PDF REPORTS ========================
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from io import BytesIO
from reportlab.platypus import Image as ReportLabImage 
import ssl
from urllib.request import Request, urlopen
from reportlab.lib.utils import ImageReader
from werkzeug.utils import secure_filename

# import qrcode

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'workzen-secret-key-2025')

# PostgreSQL Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.environ.get('DB_USER', 'postgres')}:"
    f"{os.environ.get('DB_PASSWORD', '8511')}@"
    f"{os.environ.get('DB_HOST', 'localhost')}:"
    f"{os.environ.get('DB_PORT', 5432)}/"
    f"{os.environ.get('DB_NAME', 'workzen_db')}"
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ======================== DATABASE MODELS ========================

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='STUDENT')
    full_name = db.Column(db.String(255), nullable=True)
    
    # --- CHANGED: Use ID instead of Email ---
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # ----------------------------------------

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        return self.password == password


class Attendance(db.Model):
    """Attendance tracking model"""
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50))  # Present, Absent
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'attendance_date', name='uq_user_date'),)

class Leave(db.Model):
    """Leave request model"""
    __tablename__ = 'leaves'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester = db.relationship('User', foreign_keys=[user_id])
    leave_type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(50), default='Pending')  # Pending, Approved, Rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approver = db.relationship('User', foreign_keys=[approved_by])
    number_of_days = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class LeaveBalance(db.Model):
    """Leave balance tracking"""
    __tablename__ = 'leave_balance'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)
    total_days = db.Column(db.Integer)
    used_days = db.Column(db.Integer, default=0)
    remaining_days = db.Column(db.Integer)
    year = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'leave_type', 'year', name='uq_user_leave_year'),)

class LeaveDocument(db.Model):
    """Documents attached to leave requests (Medical reports, certificates, etc.)"""
    __tablename__ = 'leave_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    leave_id = db.Column(db.Integer, db.ForeignKey('leaves.id'), nullable=False)
    leave = db.relationship('Leave', backref='documents')
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    file_name = db.Column(db.String(255), nullable=False)
    document_type = db.Column(db.String(100))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Achievement(db.Model):
    __tablename__ = 'achievements'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='achievements')
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ======================== DECORATORS ========================

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    """Decorator for role-based access"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = User.query.get(session.get('user_id'))
            if not user or user.role not in roles:
                return redirect(url_for('login')), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ======================== AUTHENTICATION ROUTES ========================

@app.route('/')
def index():
    """Redirect to login"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login with email and password"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid credentials'), 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('login'))

# ======================== DASHBOARD ========================

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page"""
    user = User.query.get(session.get('user_id'))
    return render_template('dashboard.html', user=user)

# ======================== TIME OFF (LEAVES) ========================

@app.route('/timeoff')
@login_required
def timeoff():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    current_year = datetime.now().year

    # 1. Own History
    leaves = Leave.query.filter_by(user_id=user_id).order_by(Leave.created_at.desc()).all()
    
    # 2. Balance
    leave_balance = LeaveBalance.query.filter_by(user_id=user_id, year=current_year).all()

    # 3. All Leaves (History)
    all_leaves = []
    if user.role == 'HOD':
        all_leaves = Leave.query.order_by(Leave.created_at.desc()).all()
    elif user.role == 'COUNSELOR':
        # --- CHANGED: Compare counselor_id == user.id ---
        all_leaves = Leave.query.join(User, Leave.user_id == User.id).filter(
            User.counselor_id == user.id
        ).order_by(Leave.created_at.desc()).all()
    else:
        all_leaves = [leave for leave in leaves]

    # 4. Pending Approvals
    pending_leaves = []
    approved_today = 0
    rejected_today = 0
    today = datetime.now().date()

    if user.role in ['COUNSELOR', 'HOD']:
        if user.role == 'HOD':
            pending_leaves = Leave.query.filter_by(status='Pending').order_by(Leave.created_at.desc()).all()
            approved_today = Leave.query.filter(Leave.status == 'Approved', Leave.updated_at >= today).count()
            rejected_today = Leave.query.filter(Leave.status == 'Rejected', Leave.updated_at >= today).count()

        elif user.role == 'COUNSELOR':
            # --- CHANGED: Compare counselor_id == user.id ---
            pending_leaves = Leave.query.join(User, Leave.user_id == User.id).filter(
                Leave.status == 'Pending',
                User.counselor_id == user.id
            ).order_by(Leave.created_at.desc()).all()

            approved_today = Leave.query.join(User, Leave.user_id == User.id).filter(
                Leave.status == 'Approved', Leave.updated_at >= today,
                User.counselor_id == user.id
            ).count()

            rejected_today = Leave.query.join(User, Leave.user_id == User.id).filter(
                Leave.status == 'Rejected', Leave.updated_at >= today,
                User.counselor_id == user.id
            ).count()

    return render_template('timeoff.html', user=user, leaves=leaves, leave_balance=leave_balance,
                           current_year=current_year, all_leaves=all_leaves, pending_leaves=pending_leaves,
                           pending_count=len(pending_leaves), approved_today=approved_today, rejected_today=rejected_today)
"""
@app.route('/api/leaves/apply', methods=['POST'])
@login_required
def apply_leave():
    Apply for leave with optional document upload
    try:
        user_id = session.get('user_id')
        
        # Handle form data with file
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        leave_type = request.form.get('leave_type')
        reason = request.form.get('reason')
        
        num_days = (end_date - start_date).days + 1
        current_year = datetime.now().year
        
        # Find Counselor (first available)
        counselor = User.query.filter_by(role='COUNSELOR').first()
        
        # Check or create leave balance
        balance = LeaveBalance.query.filter_by(
            user_id=user_id,
            leave_type=leave_type,
            year=current_year
        ).first()
        
        if not balance:
            default_days = {'Annual': 20, 'Sick': 10, 'Casual': 5}
            balance = LeaveBalance(
                user_id=user_id,
                leave_type=leave_type,
                total_days=default_days.get(leave_type, 5),
                used_days=0,
                remaining_days=default_days.get(leave_type, 5),
                year=current_year
            )
            db.session.add(balance)
            db.session.commit()
        
        if balance.remaining_days < num_days:
            return jsonify(
                error=f'Insufficient leave balance. Available: {balance.remaining_days} days, Requested: {num_days} days'
            ), 400
        
        # Create leave request
        leave = Leave(
            user_id=user_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            number_of_days=num_days,
            status='Pending',
            approved_by=counselor.id if counselor else None
        )
        
        db.session.add(leave)
        db.session.flush()  # Get leave ID without committing
        
        # Handle document upload if provided
        if 'document' in request.files:
            file = request.files['document']
            document_type = request.form.get('document_type', 'Supporting Document')
            
            if file and file.filename:
                # Validate PDF format
                if not file.filename.lower().endswith('.pdf'):
                    db.session.rollback()
                    return jsonify({'error': 'Only PDF files are allowed'}), 400
                
                # Check file size (5 MB max)
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                
                if file_size > 5 * 1024 * 1024:
                    db.session.rollback()
                    return jsonify({'error': 'File size exceeds 5 MB limit'}), 400
                
                # Create uploads directory
                os.makedirs('uploads/leave_documents', exist_ok=True)
                
                # Save file with secure name
                import secrets
                safe_name = f"leave_{leave.id}_{user_id}_{secrets.token_hex(8)}.pdf"
                path = os.path.join('uploads/leave_documents', safe_name)
                file.save(path)
                
                # Create LeaveDocument record
                doc = LeaveDocument(
                    leave_id=leave.id,
                    user_id=user_id,
                    file_url=f'/uploads/leave_documents/{safe_name}',
                    file_size=file_size,
                    file_name=secure_filename(file.filename),
                    document_type=document_type
                )
                db.session.add(doc)
        
        db.session.commit()
        
        return jsonify(
            message='Leave request submitted successfully',
            leave_id=leave.id
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500
"""

@app.route('/api/leaves/apply', methods=['POST'])
@login_required
def apply_leave():
    """Apply for leave with optional document upload (Unlimited Leave Enabled)"""
    try:
        user_id = session.get('user_id')

        # ================= FORM DATA =================
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        leave_type = request.form.get('leave_type')
        reason = request.form.get('reason')

        num_days = (end_date - start_date).days + 1
        current_year = datetime.now().year

        # ================= FIND COUNSELOR =================
        counselor = User.query.filter_by(role='COUNSELOR').first()

        # ================= UNLIMITED LEAVE BALANCE =================
        balance = LeaveBalance.query.filter_by(
            user_id=user_id,
            leave_type=leave_type,
            year=current_year
        ).first()

        # Create balance record only for reporting
        if not balance:
            balance = LeaveBalance(
                user_id=user_id,
                leave_type=leave_type,
                total_days=9999,        # Virtual unlimited
                used_days=0,
                remaining_days=9999,    # Never blocks leave
                year=current_year
            )
            db.session.add(balance)
            db.session.commit()

        # ❌ NO balance.remaining_days check
        # Unlimited leave – skip validation

        # ================= CREATE LEAVE REQUEST =================
        leave = Leave(
            user_id=user_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            number_of_days=num_days,
            status='Pending',
            approved_by=counselor.id if counselor else None
        )

        db.session.add(leave)
        db.session.flush()  # Get leave.id before commit

        # ================= DOCUMENT UPLOAD =================
        if 'document' in request.files:
            file = request.files['document']
            document_type = request.form.get('document_type', 'Supporting Document')

            if file and file.filename:
                if not file.filename.lower().endswith('.pdf'):
                    db.session.rollback()
                    return jsonify({'error': 'Only PDF files are allowed'}), 400

                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)

                if file_size > 5 * 1024 * 1024:
                    db.session.rollback()
                    return jsonify({'error': 'File size exceeds 5 MB limit'}), 400

                os.makedirs('uploads/leave_documents', exist_ok=True)

                import secrets
                safe_name = f"leave_{leave.id}_{user_id}_{secrets.token_hex(8)}.pdf"
                path = os.path.join('uploads/leave_documents', safe_name)
                file.save(path)

                doc = LeaveDocument(
                    leave_id=leave.id,
                    user_id=user_id,
                    file_url=f'/uploads/leave_documents/{safe_name}',
                    file_size=file_size,
                    file_name=secure_filename(file.filename),
                    document_type=document_type
                )
                db.session.add(doc)

        # ================= COMMIT =================
        db.session.commit()

        return jsonify(
            message='Leave request submitted successfully (Unlimited Leave Enabled)',
            leave_id=leave.id
        ), 201

    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500


@app.route('/api/leaves/<int:leave_id>/documents', methods=['GET'])
@login_required
def get_leave_documents(leave_id):
    """Get all documents for a specific leave request"""
    try:
        user_id = session.get('user_id')
        leave = Leave.query.get(leave_id)
        
        if not leave:
            return jsonify({'error': 'Leave request not found'}), 404
        
        # Check authorization
        user = User.query.get(user_id)
        if leave.user_id != user_id and user.role not in ['HOD', 'COUNSELOR']:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        documents = LeaveDocument.query.filter_by(leave_id=leave_id).all()
        
        return jsonify({
            'documents': [{
                'id': doc.id,
                'leave_id': doc.leave_id,
                'file_name': doc.file_name,
                'file_url': doc.file_url,
                'file_size': doc.file_size,
                'document_type': doc.document_type,
                'created_at': doc.created_at.isoformat()
            } for doc in documents]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/leaves/<int:leave_id>/documents/upload', methods=['POST'])
@login_required
def upload_leave_document(leave_id):
    """Upload a document to an existing leave request"""
    try:
        user_id = session.get('user_id')
        leave = Leave.query.get(leave_id)
        
        if not leave:
            return jsonify({'error': 'Leave request not found'}), 404
        
        if leave.user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        if leave.status != 'Pending':
            return jsonify({'error': 'Can only upload documents for pending leave requests'}), 400
        
        file = request.files.get('document')
        document_type = request.form.get('document_type', 'Supporting Document')
        
        if not file:
            return jsonify({'error': 'No file provided'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'File size exceeds 5 MB limit'}), 400
        
        os.makedirs('uploads/leave_documents', exist_ok=True)
        
        import secrets
        safe_name = f"leave_{leave_id}_{user_id}_{secrets.token_hex(8)}.pdf"
        path = os.path.join('uploads/leave_documents', safe_name)
        file.save(path)
        
        doc = LeaveDocument(
            leave_id=leave_id,
            user_id=user_id,
            file_url=f'/uploads/leave_documents/{safe_name}',
            file_size=file_size,
            file_name=secure_filename(file.filename),
            document_type=document_type
        )
        db.session.add(doc)
        db.session.commit()
        
        return jsonify({
            'message': 'Document uploaded successfully',
            'document': {
                'id': doc.id,
                'file_name': doc.file_name,
                'file_url': doc.file_url,
                'file_size': doc.file_size,
                'document_type': doc.document_type,
                'created_at': doc.created_at.isoformat()
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_leave_document(doc_id):
    """Delete a document from leave request"""
    try:
        user_id = session.get('user_id')
        doc = LeaveDocument.query.get(doc_id)
        
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
        
        if doc.user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        leave = Leave.query.get(doc.leave_id)
        if leave.status != 'Pending':
            return jsonify({'error': 'Cannot delete documents from processed leave requests'}), 400
        
        try:
            if 'uploads/leave_documents' in doc.file_url:
                file_path = doc.file_url.replace('/uploads/leave_documents/', 'uploads/leave_documents/')
                if os.path.exists(file_path):
                    os.remove(file_path)
        except:
            pass
        
        db.session.delete(doc)
        db.session.commit()
        
        return jsonify({'message': 'Document deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/uploads/leave_documents/<filename>')
@login_required
def download_leave_document(filename):
    """View a leave document inline (no download)"""
    try:
        # 1. Find the document record to check permissions
        doc = LeaveDocument.query.filter_by(file_url=f'/uploads/leave_documents/{filename}').first()
        
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
        
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        # 2. Allow access if user is Owner OR (HOD or COUNSELOR)
        if doc.user_id != user_id and user.role not in ['HOD', 'COUNSELOR']:
            return jsonify({'error': 'Unauthorized access'}), 403
            
        # 3. Serve the file INLINE (Preview)
        return send_file(
            os.path.join('uploads/leave_documents', filename),
            mimetype='application/pdf',  # Explicitly tell browser it's a PDF
            as_attachment=False          # False = Show in browser, True = Download
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/fix-database')
def fix_database():
    try:
        # This SQL command adds the missing column
        db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);"))
        db.session.commit()
        return "✅ Success! The 'full_name' column has been added to the database. You can go back to Dashboard now."
    except Exception as e:
        return f"❌ Error: {str(e)}"
    

@app.route('/api/leaves/approve/<int:leave_id>', methods=['PUT'])
@login_required
@role_required('HOD', 'COUNSELOR')
def approve_leave(leave_id):
    """Approve leave request"""
    leave = Leave.query.get(leave_id)
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404

    leave.status = 'Approved'
    leave.approved_by = session.get('user_id')
    balance = LeaveBalance.query.filter_by(
        user_id=leave.user_id,
        leave_type=leave.leave_type,
        year=datetime.now().year
    ).first()

    if balance:
        balance.used_days += leave.number_of_days
        balance.remaining_days = balance.total_days - balance.used_days

    db.session.commit()
    return jsonify({'message': 'Leave approved successfully'}), 200

@app.route('/api/leaves/reject/<int:leave_id>', methods=['PUT'])
@login_required
@role_required('HOD', 'COUNSELOR')
def reject_leave(leave_id):
    """Reject leave request"""
    leave = Leave.query.get(leave_id)
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404

    leave.status = 'Rejected'
    leave.approved_by = session.get('user_id')
    db.session.commit()
    return jsonify({'message': 'Leave rejected successfully'}), 200

# ======================== PDF REPORT GENERATION ========================

@app.route('/api/leaves/report', methods=['GET'])
@login_required


def generate_leave_report():
    """Generate comprehensive PDF report with Robust Image Loading"""
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        leaves = Leave.query.all()
        
        # Statistics
        total_leaves = len(leaves)
        pending_leaves = len([l for l in leaves if l.status == 'Pending'])
        approved_leaves = len([l for l in leaves if l.status == 'Approved'])
        rejected_leaves = len([l for l in leaves if l.status == 'Rejected'])
        
        pdf_buffer = BytesIO()

        # --- HELPER: Fetch Image safely (Bypassing SSL errors) ---
        def get_image_from_url(url):
            try:
                # Create a context that doesn't verify SSL certificates (fixes common download issues)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                # Add a User-Agent header so the server doesn't block us
                req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                
                # Read data
                response = urlopen(req, context=ctx)
                image_data = BytesIO(response.read())
                return ImageReader(image_data)
            except Exception as e:
                print(f"Error fetching image {url}: {e}")
                return None

        # --- HEADER FUNCTION ---
        def draw_header(canvas, doc):
            canvas.saveState()
            page_width, page_height = A4
            
            # 1. Define Image URLs
            mbit_url = "https://www.mbit.edu.in/wp-content/uploads/2021/12/webMBIT-1@2x.png"
            cvm_url = "https://www.mbit.edu.in/wp-content/uploads/2020/02/CVM-CVMU.jpg"
            
            # 2. Draw Left Logo (MBIT)
            logo_mbit = get_image_from_url(mbit_url)
            if logo_mbit:
                # x=20, y=Top-110, Width=180, Height=Auto
                canvas.drawImage(logo_mbit, 0.4*inch, page_height - 1.6*inch, 
                               width=2.5*inch, height=0.9*inch, 
                               mask='auto', preserveAspectRatio=True, anchor='w')
            else:
                # Fallback text
                canvas.setFont('Helvetica-Oblique', 10)
                canvas.drawString(0.5*inch, page_height - 1*inch, "MBIT")

            # 3. Draw Right Logo (CVM)
            logo_cvm = get_image_from_url(cvm_url)
            if logo_cvm:
                canvas.drawImage(logo_cvm, page_width - 1.8*inch, page_height - 1.6*inch, 
                               width=1.3*inch, height=1.3*inch, 
                               mask='auto', preserveAspectRatio=True, anchor='e')
            
            # 4. Draw Center Text
            # Institute Name
            canvas.setFont('Helvetica-Bold', 14)
            canvas.setFillColor(colors.HexColor('#1f2937'))
            
            # Center coordinates
            center_x = page_width / 2.0
            text_y = page_height - 0.8*inch
            
            canvas.drawCentredString(center_x, text_y, "Madhuben & Bhanubhai Patel")
            canvas.drawCentredString(center_x, text_y - 18, "Institute of Technology")
            
            # Subtitle
            canvas.setFont('Helvetica', 10)
            canvas.setFillColor(colors.HexColor('#6b7280'))
            canvas.drawCentredString(center_x, text_y - 35, "(The Charutar Vidya Mandal (CVM) University)")

            # 5. Separator Line
            canvas.setStrokeColor(colors.HexColor('#e5e7eb'))
            canvas.setLineWidth(1)
            canvas.line(0.5*inch, page_height - 1.8*inch, page_width - 0.5*inch, page_height - 1.8*inch)
            
            canvas.restoreState()

        # --- SETUP DOCUMENT ---
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=2.2*inch, # Space for Header
            bottomMargin=0.75*inch,
            title='Leave Management Report'
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#208099'), spaceAfter=12, spaceBefore=12)
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=10, spaceAfter=6)
        
        # Report Title
        story.append(Paragraph('Leave Management Report', heading_style))
        story.append(Paragraph(f'Generated on {datetime.now().strftime("%d %B %Y at %H:%M:%S")}', normal_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Summary Statistics
        story.append(Paragraph('Summary Statistics', heading_style))
        
        summary_data = [
            ['Metric', 'Count'],
            ['Total Leave Requests', str(total_leaves)],
            ['Pending Approvals', str(pending_leaves)],
            ['Approved Requests', str(approved_leaves)],
            ['Rejected Requests', str(rejected_leaves)],
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Detailed Leave Records
        story.append(Paragraph('Detailed Leave Records', heading_style))
        
        if leaves:
            leave_data = [['Employee', 'Leave Type', 'Start Date', 'End Date', 'Days', 'Status', 'Reason']]
            
            for leave in leaves:
                if leave.requester:
                    name = getattr(leave.requester, 'full_name', None) or leave.requester.email.split('@')[0]
                    email = leave.requester.email
                    emp_details = Paragraph(f"<b>{name}</b><br/>{email}", normal_style)
                else:
                    emp_details = 'N/A'

                leave_data.append([
                    emp_details,
                    leave.leave_type,
                    leave.start_date.strftime('%d/%m/%Y'),
                    leave.end_date.strftime('%d/%m/%Y'),
                    str(leave.number_of_days),
                    leave.status,
                    leave.reason[:30] + '...' if leave.reason and len(leave.reason) > 30 else leave.reason or 'N/A'
                ])
            
            leave_table = Table(leave_data, colWidths=[2.0*inch, 1*inch, 1*inch, 1*inch, 0.7*inch, 0.9*inch, 1.4*inch])
            leave_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
            ]))
            story.append(leave_table)
        else:
            story.append(Paragraph('No leave records found.', normal_style))
        
        story.append(Spacer(1, 0.5*inch))
        
        # Footer
        footer_text = f"""
        <b>Report Information:</b><br/>
        Generated by: {user.email}<br/>
        Role: {user.role}<br/>
        <br/>

        """
        story.append(Paragraph(footer_text, normal_style))
        
        # BUILD PDF
        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
        
        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'leave_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500   



@app.route('/api/leaves/report/filtered', methods=['POST'])
@login_required
def generate_filtered_report():
    """Generate filtered PDF report with Institutional Header"""
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        # Get filter criteria
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        status = data.get('status')
        leave_type = data.get('leave_type')
        
        # Build query
        query = Leave.query
        
        if start_date:
            query = query.filter(Leave.start_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(Leave.end_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
        if status:
            query = query.filter(Leave.status == status)
        if leave_type:
            query = query.filter(Leave.leave_type == leave_type)
            
        leaves = query.order_by(Leave.created_at.desc()).all()
        
        # Statistics for this filtered set
        total_leaves = len(leaves)
        pending_leaves = len([l for l in leaves if l.status == 'Pending'])
        approved_leaves = len([l for l in leaves if l.status == 'Approved'])
        rejected_leaves = len([l for l in leaves if l.status == 'Rejected'])
        
        pdf_buffer = BytesIO()

        # --- HELPER: Fetch Image safely ---
        def get_image_from_url(url):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urlopen(req, context=ctx)
                image_data = BytesIO(response.read())
                return ImageReader(image_data)
            except Exception:
                return None

        # --- HEADER FUNCTION (Same as Main Report) ---
        def draw_header(canvas, doc):
            canvas.saveState()
            page_width, page_height = A4
            
            # URLs
            mbit_url = "https://www.mbit.edu.in/wp-content/uploads/2021/12/webMBIT-1@2x.png"
            cvm_url = "https://www.mbit.edu.in/wp-content/uploads/2020/02/CVM-CVMU.jpg"
            
            # Left Logo (MBIT)
            logo_mbit = get_image_from_url(mbit_url)
            if logo_mbit:
                canvas.drawImage(logo_mbit, 0.4*inch, page_height - 1.6*inch, 
                               width=2.5*inch, height=0.9*inch, 
                               mask='auto', preserveAspectRatio=True, anchor='w')
            else:
                canvas.setFont('Helvetica-Oblique', 10)
                canvas.drawString(0.5*inch, page_height - 1*inch, "MBIT")

            # Right Logo (CVM)
            logo_cvm = get_image_from_url(cvm_url)
            if logo_cvm:
                canvas.drawImage(logo_cvm, page_width - 1.8*inch, page_height - 1.6*inch, 
                               width=1.3*inch, height=1.3*inch, 
                               mask='auto', preserveAspectRatio=True, anchor='e')

            # Center Text
            canvas.setFont('Helvetica-Bold', 14)
            canvas.setFillColor(colors.HexColor('#1f2937'))
            center_x = page_width / 2.0
            text_y = page_height - 0.8*inch
            
            canvas.drawCentredString(center_x, text_y, "Madhuben & Bhanubhai Patel")
            canvas.drawCentredString(center_x, text_y - 18, "Institute of Technology")
            
            canvas.setFont('Helvetica', 10)
            canvas.setFillColor(colors.HexColor('#6b7280'))
            canvas.drawCentredString(center_x, text_y - 35, "(The Charutar Vidya Mandal (CVM) University)")

            # Separator Line
            canvas.setStrokeColor(colors.HexColor('#e5e7eb'))
            canvas.setLineWidth(1)
            canvas.line(0.5*inch, page_height - 1.8*inch, page_width - 0.5*inch, page_height - 1.8*inch)
            
            canvas.restoreState()

        # --- SETUP DOCUMENT ---
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=2.2*inch,  # Consistent Header Space
            bottomMargin=0.75*inch,
            title='Filtered Leave Report'
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#208099'), spaceAfter=12, spaceBefore=12)
        normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=10, spaceAfter=6)
        
        # Report Title
        story.append(Paragraph('Filtered Leave Report', heading_style))
        story.append(Paragraph(f'Generated on {datetime.now().strftime("%d %B %Y at %H:%M:%S")}', normal_style))
        
        # Show Filters Applied
        filter_text = []
        if start_date: filter_text.append(f"From: {start_date}")
        if end_date: filter_text.append(f"To: {end_date}")
        if status: filter_text.append(f"Status: {status}")
        if leave_type: filter_text.append(f"Type: {leave_type}")
        
        if filter_text:
            story.append(Paragraph(f"<b>Filters:</b> {', '.join(filter_text)}", normal_style))
            
        story.append(Spacer(1, 0.2*inch))
        
        # Summary Statistics Table
        story.append(Paragraph('Summary Statistics', heading_style))
        summary_data = [
            ['Metric', 'Count'],
            ['Total Requests', str(total_leaves)],
            ['Pending', str(pending_leaves)],
            ['Approved', str(approved_leaves)],
            ['Rejected', str(rejected_leaves)],
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Detailed Records Table
        story.append(Paragraph('Detailed Leave Records', heading_style))
        
        if leaves:
            leave_data = [['Employee', 'Leave Type', 'Start Date', 'End Date', 'Days', 'Status', 'Reason']]
            
            for leave in leaves:
                if leave.requester:
                    name = getattr(leave.requester, 'full_name', None) or leave.requester.email.split('@')[0]
                    email = leave.requester.email
                    emp_details = Paragraph(f"<b>{name}</b><br/>{email}", normal_style)
                else:
                    emp_details = 'N/A'

                leave_data.append([
                    emp_details,
                    leave.leave_type,
                    leave.start_date.strftime('%d/%m/%Y'),
                    leave.end_date.strftime('%d/%m/%Y'),
                    str(leave.number_of_days),
                    leave.status,
                    leave.reason[:30] + '...' if leave.reason and len(leave.reason) > 30 else leave.reason or 'N/A'
                ])
            
            leave_table = Table(leave_data, colWidths=[2.0*inch, 1*inch, 1*inch, 1*inch, 0.7*inch, 0.9*inch, 1.4*inch])
            leave_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
            ]))
            story.append(leave_table)
        else:
            story.append(Paragraph('No records match these filters.', normal_style))
        
        story.append(Spacer(1, 0.5*inch))
        
        # Footer
        footer_text = f"""
        <b>Report Information:</b><br/>
        Generated by: {user.email}<br/>
        Role: {user.role}<br/>
        <br/>
        <i>This is an auto-generated report. Please verify the data before taking any action.</i>
        """
        story.append(Paragraph(footer_text, normal_style))
        
        # BUILD PDF
        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
        
        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'filtered_leave_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500

# ======================== SICK LEAVE PDF UPLOAD ========================

class MedicalRecord(db.Model):
    """Medical certificate for sick leave"""
    __tablename__ = 'medical_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), default='Sick')
    reason = db.Column(db.Text)
    file_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@app.route('/api/sick-leave/upload-certificate', methods=['POST'])
@login_required
def upload_sick_certificate():
    """Upload medical certificate for sick leave"""
    try:
        user_id = session.get('user_id')
        file = request.files.get('file')
        reason = request.form.get('reason')
        
        if not file or not reason:
            return jsonify({'error': 'Missing file or reason'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files allowed'}), 400
        
        # Check file size (5 MB)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'File size exceeds 5 MB'}), 400
        
        os.makedirs('uploads/medical', exist_ok=True)
        
        import secrets
        safe_name = f"{user_id}_{secrets.token_hex(8)}.pdf"
        path = os.path.join('uploads/medical', safe_name)
        
        file.save(path)
        
        record = MedicalRecord(
            user_id=user_id,
            reason=reason,
            file_url=f'/uploads/medical/{safe_name}',
            file_size=file_size
        )
        
        db.session.add(record)
        db.session.commit()
        
        return jsonify({'message': 'Certificate uploaded successfully'}), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sick-leave/medical-records', methods=['GET'])
@login_required
def get_medical_records():
    """Get user's medical records"""
    user_id = session.get('user_id')
    records = MedicalRecord.query.filter_by(user_id=user_id).order_by(MedicalRecord.created_at.desc()).all()
    
    return jsonify({
        'records': [
            {
                'id': r.id,
                'reason': r.reason,
                'file_url': r.file_url,
                'created_at': r.created_at.isoformat(),
                'file_size': r.file_size
            }
            for r in records
        ]
    }), 200

@app.route('/api/sick-leave/medical-records/<int:record_id>', methods=['DELETE'])
@login_required
def delete_medical_record(record_id):
    """Delete medical record"""
    user_id = session.get('user_id')
    record = MedicalRecord.query.filter_by(id=record_id, user_id=user_id).first()
    
    if not record:
        return jsonify({'error': 'Record not found'}), 404
    
    # Delete file from disk
    try:
        if 'uploads/medical' in record.file_url:
            file_path = record.file_url.replace('/uploads/medical/', 'uploads/medical/')
            if os.path.exists(file_path):
                os.remove(file_path)
    except:
        pass
    
    db.session.delete(record)
    db.session.commit()
    
    return jsonify({'message': 'Record deleted'}), 200

@app.route('/uploads/medical/<filename>')
@login_required
def download_medical_record(filename):
    """Download medical record PDF"""
    return send_file(os.path.join('uploads/medical', filename), as_attachment=True)

# ======================== REPORTS ========================

@app.route('/reports')
@login_required
@role_required('HOD', 'COUNSELOR')
def reports():
    """Reports page"""
    user = User.query.get(session.get('user_id'))

    # Get attendance data
    today = datetime.now().date()
    month_start = today.replace(day=1)
    total_students = User.query.filter_by(role='STUDENT').count()
    present_today = Attendance.query.filter(
        Attendance.attendance_date == today,
        Attendance.status == 'Present'
    ).count()
    pending_leaves = Leave.query.filter_by(status='Pending').count()
    approved_leaves = Leave.query.filter_by(status='Approved').count()

    return render_template('reports.html',
                          user=user,
                          total_students=total_students,
                          present_today=present_today,
                          pending_leaves=pending_leaves,
                          approved_leaves=approved_leaves)


@app.route('/reports/<report_type>')
@login_required
@role_required('HOD', 'COUNSELOR')
def report_detail(report_type):
    """Detailed report view"""
    user = User.query.get(session.get('user_id'))
    
    if report_type == 'attendance':
        attendance_data = Attendance.query.all()
        return render_template('report_detail.html', 
                             report_type=report_type,
                             data=attendance_data,
                             user=user)
    
    elif report_type == 'leaves':
        leave_data = Leave.query.all()
        return render_template('report_detail.html',
                             report_type=report_type,
                             data=leave_data,
                             user=user)
    
    else:
        return redirect(url_for('reports'))


# ======================== PROFILE ROUTE ========================
@app.route('/profile')
@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id=None):  # <--- KEY FIX: Set default value to None
    # 1. Get the Logged-in User (This ensures the Sidebar works correctly)
    logged_in_id = session.get('user_id')
    logged_in_user = User.query.get(logged_in_id)

    # 2. Determine which user's profile to show
    if user_id is None:
        # Case A: User visited '/profile' -> Show their own profile
        profile_user = logged_in_user
    else:
        # Case B: User visited '/profile/123' -> Show that specific student
        profile_user = User.query.get_or_404(user_id)

    # 3. Check if we are viewing someone else's profile
    # If IDs match, it's my profile (Editable). If not, it's view-only.
    view_only = (logged_in_user.id != profile_user.id)

    # 4. Pass variables to template
    # 'user'    -> Sent to base.html (Keeps the Sidebar/Menu correct)
    # 'student' -> Sent to profile.html (Shows the profile data)
    return render_template('profile.html', 
                           user=logged_in_user, 
                           student=profile_user, 
                           view_only=view_only)

# ======================== PROFILE API ROUTES ========================

# 1. CHANGE PASSWORD (Fixed URL to match profile.html)
@app.route('/api/change_password', methods=['POST'])
@login_required
def change_password():
    """Handle Password Change"""
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        # Check keys sent from HTML: 'old_password' and 'new_password'
        if not user.check_password(data.get('old_password')):
            return jsonify({'error': 'Incorrect current password'}), 400
            
        user.set_password(data.get('new_password'))
        db.session.commit()
        
        return jsonify({'message': 'Password updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 2. GET ACHIEVEMENTS (This was missing! That's why they didn't show up)
@app.route('/api/achievements', methods=['GET'])
@login_required
def get_achievements():
    """Fetch achievements list"""
    try:
        # Get ID from URL parameter (e.g. ?user_id=5) or default to logged-in user
        user_id = request.args.get('user_id', type=int, default=session.get('user_id'))
        
        achievements = Achievement.query.filter_by(user_id=user_id).order_by(Achievement.created_at.desc()).all()
        
        return jsonify({
            'achievements': [{
                'id': ach.id,
                'title': ach.title,
                'description': ach.description,
                'file_url': ach.file_url,
                'created_at': ach.created_at.isoformat() if ach.created_at else ''
            } for ach in achievements]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 3. UPLOAD ACHIEVEMENT
@app.route('/api/achievements/upload', methods=['POST'])
@login_required
def upload_achievement():
    """Upload a new achievement with PDF"""
    try:
        # Allow uploading for other users (if HOD/Counselor) or self
        current_user_id = session.get('user_id')
        target_user_id = request.args.get('user_id', type=int, default=current_user_id)
        
        title = request.form.get('title')
        description = request.form.get('description')
        file = request.files.get('file')

        if not file or not title:
            return jsonify({'error': 'Missing file or title'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files allowed'}), 400
            
        # Save File
        import secrets
        os.makedirs('uploads/achievements', exist_ok=True)
        safe_name = f"ach_{target_user_id}_{secrets.token_hex(8)}.pdf"
        file_path = os.path.join('uploads/achievements', safe_name)
        file.save(file_path)

        # Save to DB
        achievement = Achievement(
            user_id=target_user_id,
            title=title,
            description=description,
            file_url=f"/uploads/achievements/{safe_name}",
            file_size=os.path.getsize(file_path)
        )
        db.session.add(achievement)
        db.session.commit()

        return jsonify({'message': 'Achievement added successfully'}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 4. DELETE ACHIEVEMENT
@app.route('/api/achievements/<int:id>', methods=['DELETE'])
@login_required
def delete_achievement(id):
    """Delete an achievement"""
    try:
        ach = Achievement.query.get(id)
        if not ach:
            return jsonify({'error': 'Not found'}), 404
            
        # Security: Allow if it's your own achievement OR you are HOD
        current_user = User.query.get(session.get('user_id'))
        if ach.user_id != current_user.id and current_user.role != 'HOD':
            return jsonify({'error': 'Unauthorized'}), 403

        # Delete file
        try:
            # Remove leading slash for file system path
            file_path = ach.file_url.lstrip('/')
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass 

        db.session.delete(ach)
        db.session.commit()
        return jsonify({'message': 'Deleted successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 5. SERVE PDF FILES
@app.route('/uploads/achievements/<filename>')
@login_required
def uploaded_achievement_file(filename):
    # This allows the "View PDF" button to work
    return send_file(os.path.join('uploads/achievements', filename))


# ======================== STUDENTS LIST ROUTE ========================

@app.route('/students')
@login_required
def students_list():
    # 1. Fetch current user manually
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)

    if not current_user:
        return redirect(url_for('login'))

    # 2. Logic to get list of students (Case Insensitive)
    user_role = current_user.role.upper() # Converts 'Counselor' -> 'COUNSELOR'

    if user_role == 'HOD':
        students = User.query.filter(User.role.ilike('Student')).all()
    elif user_role == 'COUNSELOR':
        students = User.query.filter_by(counselor_id=current_user.id).all()
    else:
        return redirect(url_for('dashboard'))
    
    # 3. PASS 'user=current_user' so the sidebar works!
    return render_template('students.html', students=students, user=current_user)



# ======================== UPDATED API: FETCH ACHIEVEMENTS ========================
@app.route('/api/achievements/list')
@login_required
def get_achievements_list():
    # --- FIX START: Get the current user BEFORE doing anything else ---
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)

    if not current_user:
        return jsonify({'error': 'User session not found'}), 404
    # --- FIX END ----------------------------------------------------

    # 1. Check if we are looking for a specific student's achievements
    target_user_id = request.args.get('user_id', type=int)
    
    # If no ID provided, default to the logged-in user
    if not target_user_id:
        target_user_id = current_user.id

    # 2. Permission Check: Are we allowed to view this person?
    if target_user_id != current_user.id:
        target_user = User.query.get(target_user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Allow HOD (any case) or Assigned Counselor (any case)
        is_authorized = (
            current_user.role in ['HOD', 'Hod', 'hod'] or 
            (current_user.role in ['Counselor', 'COUNSELOR', 'counselor'] and target_user.counselor_id == current_user.id)
        )
        
        if not is_authorized:
            return jsonify({'error': 'Unauthorized to view these achievements'}), 403
            
        user_id_to_fetch = target_user_id
    else:
        user_id_to_fetch = current_user.id

    # 3. Fetch the achievements
    achievements = Achievement.query.filter_by(user_id=user_id_to_fetch).order_by(Achievement.created_at.desc()).all()
    
    return jsonify({
        'achievements': [{
            'id': a.id,
            'title': a.title,
            'description': a.description,
            'file_url': a.file_url,
            'created_at': a.created_at.isoformat()
        } for a in achievements]
    })

# ======================== UPDATED REPORT GENERATION ========================
import requests
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import Image as ReportLabImage
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
from datetime import datetime
from flask import send_file, session, jsonify

# ======================== UPDATED PDF REPORT ROUTE ========================
@app.route('/api/reports/download/<report_type>/pdf')
@login_required
def download_report_pdf(report_type):
    """Generate PDF Report with Header like Base.html and Detailed Columns"""
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        # 1. Fetch Data
        if report_type == 'leaves':
            if user.role == 'HOD':
                data = Leave.query.join(User).order_by(Leave.created_at.desc()).all()
            elif user.role == 'COUNSELOR':
                data = Leave.query.join(User).filter(User.counselor_id == user.id).order_by(Leave.created_at.desc()).all()
            else:
                data = Leave.query.filter_by(user_id=user.id).order_by(Leave.created_at.desc()).all()
                
            # --- COLUMNS: Added Name & Email ---
            table_headers = ['Student Name', 'Email', 'Type', 'Start Date', 'End Date', 'Days', 'Status']
            
            table_data = []
            for leave in data:
                table_data.append([
                    leave.requester.full_name or "N/A",  # Name from relationship
                    leave.requester.email or "N/A",      # Email from relationship
                    leave.leave_type,
                    leave.start_date.strftime('%Y-%m-%d'),
                    leave.end_date.strftime('%Y-%m-%d'),
                    str(leave.number_of_days),
                    leave.status
                ])
        else:
            return jsonify({'error': 'Invalid report type'}), 400

        # 2. Setup PDF (Landscape)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), topMargin=1.5*inch)
        elements = []

        # 3. Header Function (Draws Logos & Text)
        def draw_header(canvas, doc):
            canvas.saveState()
            width, height = doc.pagesize
            logo_width = 1.2 * inch
            logo_height = 1.0 * inch
            margin = 30
            
            # Left Logo (MBIT)
            try:
                mbit_url = "https://www.mbit.edu.in/wp-content/uploads/2021/12/webMBIT-1@2x.png"
                img_data = requests.get(mbit_url).content
                img = ReportLabImage(BytesIO(img_data), width=logo_width, height=logo_height)
                img.drawOn(canvas, margin, height - logo_height - margin)
            except: pass

            # Center Text
            text_y = height - margin - 30
            canvas.setFont("Helvetica-Bold", 16)
            canvas.drawCentredString(width / 2, text_y, "Madhuben & Bhanubhai Patel Institute of Technology")
            canvas.setFont("Helvetica", 12)
            canvas.drawCentredString(width / 2, text_y - 20, "(The Charutar Vidya Mandal (CVM) University)")
            canvas.setFont("Helvetica-Bold", 14)
            canvas.drawCentredString(width / 2, text_y - 45, f"{report_type.upper()} REPORT")

            # Right Logo (CVM)
            try:
                cvm_url = "https://www.mbit.edu.in/wp-content/uploads/2020/02/CVM-CVMU.jpg"
                img_data = requests.get(cvm_url).content
                img = ReportLabImage(BytesIO(img_data), width=logo_width, height=logo_height)
                img.drawOn(canvas, width - logo_width - margin, height - logo_height - margin)
            except: pass

            # Line
            canvas.setStrokeColor(colors.black)
            canvas.line(margin, height - logo_height - margin - 10, width - margin, height - logo_height - margin - 10)
            canvas.restoreState()

        # 4. Build Table
        final_data = [table_headers] + table_data
        # Adjusted column widths for landscape
        col_widths = [2*inch, 2.5*inch, 1.2*inch, 1.2*inch, 1.2*inch, 0.8*inch, 1*inch]
        
        table = Table(final_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 1), (1, -1), 'LEFT'), # Left align Name/Email
        ]))
        
        elements.append(table)
        doc.build(elements, onFirstPage=draw_header, onLaterPages=draw_header)
        
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"{report_type}_report.pdf", mimetype='application/pdf')

    except Exception as e:
        print(f"PDF Error: {e}")
        return jsonify({'error': str(e)}), 500

# ======================== ERROR HANDLERS ========================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# ======================== ASSIGNMENT ROUTE ========================

@app.route('/api/assign_counselor', methods=['POST'])
@login_required
def assign_counselor_to_student():
    # ... (auth checks) ...
    user_id = session.get('user_id')
    curr_user = User.query.get(user_id)
    if curr_user.role != 'HOD': return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    student = User.query.filter_by(email=data.get('student_email')).first()
    counselor = User.query.filter_by(email=data.get('counselor_email')).first()

    if not student or not counselor: return jsonify({'error': 'User not found'}), 404
        
    # --- CHANGED: Save the ID ---
    student.counselor_id = counselor.id 
    db.session.commit()

    return jsonify({'message': f'Assigned {student.email} to {counselor.email}'})

# ======================== DATABASE INITIALIZATION ========================

def init_db():
    """Create all database tables"""
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)