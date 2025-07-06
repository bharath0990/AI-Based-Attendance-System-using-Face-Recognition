import cv2
import face_recognition
import numpy as np
import sqlite3
from datetime import datetime, date
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import threading
import pandas as pd
from config import Config
import logging
import shutil
import json
import time

# Add at the top of the file, after imports
_tk_image_refs = {}

class AttendanceSystem:
    def __init__(self):
        self.config = Config()
        self.setup_logging()
        self.setup_database()
        self.setup_directories()
        
        # Face recognition variables
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        
        # Camera variables
        self.camera = None
        self.camera_running = False
        
        # Threading lock for DB
        self.db_lock = threading.Lock()
        
        # Load known faces
        self.load_known_faces()
        
        # Setup GUI
        self.setup_gui()
        
        # In __init__:
        self.frame_count = 0
        
        # Added for the new camera loop logic
        self.last_face_locations = []
        self.last_face_names = []
        
    def setup_logging(self):
        """Setup logging configuration"""
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'logs/attendance_{date.today()}.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_directories(self):
        """Create necessary directories"""
        directories = ['student_images', 'reports', 'temp', 'logs', 'backup', 'database']
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            
    def setup_database(self):
        """Initialize SQLite database"""
        os.makedirs('database', exist_ok=True)
        self.conn = sqlite3.connect('database/attendance_system.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Create tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                roll_number TEXT UNIQUE NOT NULL,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                date DATE,
                time_in TIME,
                time_out TIME,
                status TEXT DEFAULT 'Present',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students (id)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS face_encodings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                encoding BLOB,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students (id)
            )
        ''')
        
        self.conn.commit()
        
    def load_known_faces(self):
        """Load known faces from database"""
        with self.db_lock:
            self.cursor.execute("SELECT fe.encoding, s.name, s.id FROM face_encodings fe JOIN students s ON fe.student_id = s.id")
            results = self.cursor.fetchall()
        
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        
        for encoding_blob, name, student_id in results:
            encoding = np.frombuffer(encoding_blob, dtype=np.float64)
            encoding = encoding.reshape((128,))  # Ensure correct shape
            self.known_face_encodings.append(encoding)
            self.known_face_names.append(name)
            self.known_face_ids.append(student_id)
        
        self.logger.info(f"Loaded {len(self.known_face_encodings)} known faces")
        
    def setup_gui(self):
        """Setup the main GUI"""
        self.root = tk.Tk()
        self.root.title("AI Attendance System")
        self.root.geometry("1200x800")
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_attendance_tab()
        self.create_student_tab()
        self.create_reports_tab()
        self.create_settings_tab()
        
    def create_attendance_tab(self):
        """Create attendance tracking tab"""
        self.attendance_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.attendance_frame, text="Attendance")
        
        # Camera frame
        self.camera_frame = ttk.LabelFrame(self.attendance_frame, text="Camera Feed")
        self.camera_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        
        # Camera display
        self.camera_label = ttk.Label(self.camera_frame)
        self.camera_label.pack(pady=10)
        
        # Camera controls
        self.camera_controls = ttk.Frame(self.camera_frame)
        self.camera_controls.pack(pady=10)
        
        self.start_camera_btn = ttk.Button(self.camera_controls, text="Start Camera", command=self.start_camera)
        self.start_camera_btn.pack(side='left', padx=5)
        
        self.stop_camera_btn = ttk.Button(self.camera_controls, text="Stop Camera", command=self.stop_camera)
        self.stop_camera_btn.pack(side='left', padx=5)
        
        # Attendance info frame
        self.info_frame = ttk.LabelFrame(self.attendance_frame, text="Attendance Information")
        self.info_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # Today's attendance
        self.today_label = ttk.Label(self.info_frame, text=f"Today's Date: {date.today()}", font=('Arial', 12, 'bold'))
        self.today_label.pack(pady=10)
        
        # Attendance list
        self.attendance_tree = ttk.Treeview(self.info_frame, columns=('Name', 'Roll', 'Time', 'Status'), show='headings')
        self.attendance_tree.heading('Name', text='Name')
        self.attendance_tree.heading('Roll', text='Roll Number')
        self.attendance_tree.heading('Time', text='Time')
        self.attendance_tree.heading('Status', text='Status')
        self.attendance_tree.pack(fill='both', expand=True, pady=10)
        
        # Refresh button
        self.refresh_btn = ttk.Button(self.info_frame, text="Refresh Attendance", command=self.refresh_attendance)
        self.refresh_btn.pack(pady=5)
        
        # Load today's attendance
        self.refresh_attendance()
        
    def create_student_tab(self):
        """Create student management tab"""
        self.student_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.student_frame, text="Students")
        
        # Student form
        self.form_frame = ttk.LabelFrame(self.student_frame, text="Add/Edit Student")
        self.form_frame.pack(fill='x', padx=5, pady=5)
        
        # Form fields
        ttk.Label(self.form_frame, text="Name:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.name_entry = ttk.Entry(self.form_frame, width=30)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(self.form_frame, text="Roll Number:").grid(row=0, column=2, sticky='w', padx=5, pady=5)
        self.roll_entry = ttk.Entry(self.form_frame, width=20)
        self.roll_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(self.form_frame, text="Email:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.email_entry = ttk.Entry(self.form_frame, width=30)
        self.email_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(self.form_frame, text="Phone:").grid(row=1, column=2, sticky='w', padx=5, pady=5)
        self.phone_entry = ttk.Entry(self.form_frame, width=20)
        self.phone_entry.grid(row=1, column=3, padx=5, pady=5)
        
        # Image upload
        self.image_frame = ttk.Frame(self.form_frame)
        self.image_frame.grid(row=2, column=0, columnspan=4, pady=10)
        
        self.upload_btn = ttk.Button(self.image_frame, text="Upload Photo", command=self.upload_student_photo)
        self.upload_btn.pack(side='left', padx=5)
        
        self.image_path_label = ttk.Label(self.image_frame, text="No image selected")
        self.image_path_label.pack(side='left', padx=5)
        
        # Form buttons
        self.button_frame = ttk.Frame(self.form_frame)
        self.button_frame.grid(row=3, column=0, columnspan=4, pady=10)
        
        self.add_student_btn = ttk.Button(self.button_frame, text="Add Student", command=self.add_student)
        self.add_student_btn.pack(side='left', padx=5)
        
        self.update_student_btn = ttk.Button(self.button_frame, text="Update Student", command=self.update_student)
        self.update_student_btn.pack(side='left', padx=5)
        
        self.clear_form_btn = ttk.Button(self.button_frame, text="Clear Form", command=self.clear_student_form)
        self.clear_form_btn.pack(side='left', padx=5)
        
        # Students list
        self.students_list_frame = ttk.LabelFrame(self.student_frame, text="Students List")
        self.students_list_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.students_tree = ttk.Treeview(self.students_list_frame, columns=('ID', 'Name', 'Roll', 'Email', 'Phone'), show='headings')
        self.students_tree.heading('ID', text='ID')
        self.students_tree.heading('Name', text='Name')
        self.students_tree.heading('Roll', text='Roll Number')
        self.students_tree.heading('Email', text='Email')
        self.students_tree.heading('Phone', text='Phone')
        self.students_tree.pack(fill='both', expand=True)
        
        # Bind double-click to edit
        self.students_tree.bind('<Double-1>', self.on_student_select)
        
        # Student management buttons
        self.student_buttons_frame = ttk.Frame(self.students_list_frame)
        self.student_buttons_frame.pack(pady=5)
        
        self.delete_student_btn = ttk.Button(self.student_buttons_frame, text="Delete Selected", command=self.delete_student)
        self.delete_student_btn.pack(side='left', padx=5)
        
        self.refresh_students_btn = ttk.Button(self.student_buttons_frame, text="Refresh List", command=self.refresh_students)
        self.refresh_students_btn.pack(side='left', padx=5)
        
        # Load students
        self.refresh_students()
        
    def create_reports_tab(self):
        """Create reports tab"""
        self.reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.reports_frame, text="Reports")
        
        # Report controls
        self.report_controls = ttk.LabelFrame(self.reports_frame, text="Generate Reports")
        self.report_controls.pack(fill='x', padx=5, pady=5)
        
        # Date selection
        ttk.Label(self.report_controls, text="From Date:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.from_date_entry = ttk.Entry(self.report_controls, width=15)
        self.from_date_entry.grid(row=0, column=1, padx=5, pady=5)
        self.from_date_entry.insert(0, str(date.today()))
        
        ttk.Label(self.report_controls, text="To Date:").grid(row=0, column=2, sticky='w', padx=5, pady=5)
        self.to_date_entry = ttk.Entry(self.report_controls, width=15)
        self.to_date_entry.grid(row=0, column=3, padx=5, pady=5)
        self.to_date_entry.insert(0, str(date.today()))
        
        # Report buttons
        self.report_buttons = ttk.Frame(self.report_controls)
        self.report_buttons.grid(row=1, column=0, columnspan=4, pady=10)
        
        self.daily_report_btn = ttk.Button(self.report_buttons, text="Daily Report", command=self.generate_daily_report)
        self.daily_report_btn.pack(side='left', padx=5)
        
        self.student_report_btn = ttk.Button(self.report_buttons, text="Student Report", command=self.generate_student_report)
        self.student_report_btn.pack(side='left', padx=5)
        
        self.export_excel_btn = ttk.Button(self.report_buttons, text="Export to Excel", command=self.export_to_excel)
        self.export_excel_btn.pack(side='left', padx=5)
        
        # Report display
        self.report_display = ttk.LabelFrame(self.reports_frame, text="Report Data")
        self.report_display.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.report_tree = ttk.Treeview(self.report_display, show='headings')
        self.report_tree.pack(fill='both', expand=True)
        
    def create_settings_tab(self):
        """Create settings tab"""
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Settings")
        
        # Database management
        self.db_frame = ttk.LabelFrame(self.settings_frame, text="Database Management")
        self.db_frame.pack(fill='x', padx=5, pady=5)
        
        self.backup_btn = ttk.Button(self.db_frame, text="Backup Database", command=self.backup_database)
        self.backup_btn.pack(side='left', padx=5, pady=5)
        
        self.restore_btn = ttk.Button(self.db_frame, text="Restore Database", command=self.restore_database)
        self.restore_btn.pack(side='left', padx=5, pady=5)
        
        # System info
        self.info_frame = ttk.LabelFrame(self.settings_frame, text="System Information")
        self.info_frame.pack(fill='x', padx=5, pady=5)
        
        self.info_text = tk.Text(self.info_frame, height=10, width=50)
        self.info_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Load system info
        self.load_system_info()
        
    def start_camera(self):
        """Start camera for attendance"""
        if not self.camera_running:
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                self.logger.error("Camera could not be opened. It may be in use by another application or not connected.")
                messagebox.showerror("Camera Error", "Camera could not be opened. Please check your camera device.")
                return
            self.camera_running = True
            self.camera_thread = threading.Thread(target=self.camera_loop)
            self.camera_thread.daemon = True
            self.camera_thread.start()
            self.logger.info("Camera started")
            
    def stop_camera(self):
        """Stop camera"""
        if self.camera_running:
            self.camera_running = False
            if self.camera:
                self.camera.release()
            self.camera_label.configure(image='')
            self.logger.info("Camera stopped")
            
    def camera_loop(self):
        """Main camera loop for face recognition"""
        while self.camera_running:
            try:
                if self.camera is None:
                    time.sleep(0.1)
                    continue
                ret, frame = self.camera.read()
                if not ret:
                    self.logger.warning("Failed to read frame from camera.")
                    time.sleep(0.1)
                    continue
                self.frame_count += 1
                process_this_frame = (self.frame_count % 3 == 0)  # Process every 3rd frame instead of 5th
                face_locations = []
                face_encodings = []
                face_names = []
                if process_this_frame:
                    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    face_locations = face_recognition.face_locations(rgb_small_frame)
                    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
                    self.logger.info(f"Detected {len(face_locations)} face(s) in frame.")
                    for face_encoding in face_encodings:
                        matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding)
                        name = "Unknown"
                        student_id = None
                        if True in matches:
                            first_match_index = matches.index(True)
                            name = self.known_face_names[first_match_index]
                            student_id = self.known_face_ids[first_match_index]
                            self.logger.info(f"Face recognized as {name}.")
                            self.mark_attendance(student_id, name)
                        else:
                            self.logger.info("Face not recognized (Unknown).")
                        face_names.append(name)
                    self.last_face_locations = face_locations
                    self.last_face_names = face_names
                else:
                    face_locations = self.last_face_locations
                    face_names = self.last_face_names
                # Draw rectangles and labels
                for i, (top, right, bottom, left) in enumerate(face_locations):
                    top *= 4
                    right *= 4
                    bottom *= 4
                    left *= 4
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    name = face_names[i] if i < len(face_names) else "Unknown"
                    cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                    font = cv2.FONT_HERSHEY_DUPLEX
                    cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.8, (255, 255, 255), 1)
                # Convert to PhotoImage and schedule GUI update using after
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_pil = Image.fromarray(frame_rgb)
                frame_pil = frame_pil.resize((640, 480))
                photo = ImageTk.PhotoImage(frame_pil)
                def update_gui(photo=photo):
                    self.camera_label.configure(image=photo)
                    _tk_image_refs[id(self.camera_label)] = photo  # Keep reference to avoid GC
                self.root.after(0, update_gui)
                time.sleep(0.005)  # Reduced sleep time for better responsiveness
            except Exception as e:
                self.logger.error(f"Error in camera loop: {e}")
                time.sleep(0.1)
                
    def mark_attendance(self, student_id, name):
        """Mark attendance for a student"""
        today = date.today().isoformat()
        current_time = datetime.now().strftime('%H:%M:%S')
        
        # Check if already marked today
        with self.db_lock:
            self.cursor.execute("SELECT * FROM attendance WHERE student_id = ? AND date = ?", (student_id, today))
            existing = self.cursor.fetchone()
        
        if not existing:
            with self.db_lock:
                self.cursor.execute("""
                    INSERT INTO attendance (student_id, date, time_in, status)
                    VALUES (?, ?, ?, 'Present')
                """, (student_id, today, current_time))
                self.conn.commit()
            self.logger.info(f"Attendance marked for {name} at {current_time}")
            self.refresh_attendance()
        else:
            self.logger.info(f"Attendance already marked for {name} today")
            
    def upload_student_photo(self):
        """Upload student photo"""
        file_path = filedialog.askopenfilename(
            title="Select Student Photo",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")]
        )
        
        if file_path:
            self.selected_image_path = file_path
            self.image_path_label.config(text=os.path.basename(file_path))
            
    def add_student(self):
        """Add new student"""
        name = self.name_entry.get().strip()
        roll = self.roll_entry.get().strip()
        email = self.email_entry.get().strip()
        phone = self.phone_entry.get().strip()
        
        if not name or not roll:
            messagebox.showerror("Error", "Name and Roll Number are required!")
            return
            
        if not hasattr(self, 'selected_image_path'):
            messagebox.showerror("Error", "Please upload a photo!")
            return
            
        try:
            # Insert student
            with self.db_lock:
                self.cursor.execute("""
                    INSERT INTO students (name, roll_number, email, phone)
                    VALUES (?, ?, ?, ?)
                """, (name, roll, email, phone))
                student_id = self.cursor.lastrowid
            
            # Process face encoding
            image = face_recognition.load_image_file(self.selected_image_path)
            face_encodings = face_recognition.face_encodings(image)
            
            if face_encodings:
                # Save image
                image_filename = f"{student_id}_{roll}.jpg"
                image_path = os.path.join('student_images', image_filename)
                shutil.copy2(self.selected_image_path, image_path)
                
                # Save face encoding
                encoding_blob = face_encodings[0].tobytes()
                with self.db_lock:
                    self.cursor.execute("""
                        INSERT INTO face_encodings (student_id, encoding, image_path)
                        VALUES (?, ?, ?)
                    """, (student_id, encoding_blob, image_path))
                    self.conn.commit()
                self.load_known_faces()  # Reload faces
                self.refresh_students()
                self.clear_student_form()
                messagebox.showinfo("Success", "Student added successfully!")
                self.logger.info(f"Student added: {name} ({roll})")
            else:
                messagebox.showerror("Error", "No face detected in the image!")
                
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Roll number already exists!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add student: {str(e)}")
            
    def update_student(self):
        """Update existing student"""
        selected = self.students_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a student to update!")
            return
            
        student_id = self.students_tree.item(selected[0])['values'][0]
        
        name = self.name_entry.get().strip()
        roll = self.roll_entry.get().strip()
        email = self.email_entry.get().strip()
        phone = self.phone_entry.get().strip()
        
        if not name or not roll:
            messagebox.showerror("Error", "Name and Roll Number are required!")
            return
            
        try:
            with self.db_lock:
                self.cursor.execute("""
                    UPDATE students SET name = ?, roll_number = ?, email = ?, phone = ?
                    WHERE id = ?
                """, (name, roll, email, phone, student_id))
                self.conn.commit()
            self.refresh_students()
            self.clear_student_form()
            messagebox.showinfo("Success", "Student updated successfully!")
            self.logger.info(f"Student updated: {name} ({roll})")
            
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Roll number already exists!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update student: {str(e)}")
            
    def delete_student(self):
        """Delete selected student"""
        selected = self.students_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a student to delete!")
            return
            
        if messagebox.askyesno("Confirm", "Are you sure you want to delete this student?"):
            student_id = self.students_tree.item(selected[0])['values'][0]
            
            try:
                with self.db_lock:
                    # Delete face encodings
                    self.cursor.execute("DELETE FROM face_encodings WHERE student_id = ?", (student_id,))
                    # Delete attendance records
                    self.cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
                    # Delete student
                    self.cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
                    self.conn.commit()
                self.load_known_faces()  # Reload faces
                self.refresh_students()
                messagebox.showinfo("Success", "Student deleted successfully!")
                self.logger.info(f"Student deleted: ID {student_id}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete student: {str(e)}")
                
    def clear_student_form(self):
        """Clear student form"""
        self.name_entry.delete(0, tk.END)
        self.roll_entry.delete(0, tk.END)
        self.email_entry.delete(0, tk.END)
        self.phone_entry.delete(0, tk.END)
        self.image_path_label.config(text="No image selected")
        if hasattr(self, 'selected_image_path'):
            delattr(self, 'selected_image_path')
            
    def on_student_select(self, event):
        """Handle student selection for editing"""
        selected = self.students_tree.selection()
        if selected:
            values = self.students_tree.item(selected[0])['values']
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, values[1])
            self.roll_entry.delete(0, tk.END)
            self.roll_entry.insert(0, values[2])
            self.email_entry.delete(0, tk.END)
            self.email_entry.insert(0, values[3])
            self.phone_entry.delete(0, tk.END)
            self.phone_entry.insert(0, values[4])
            
    def refresh_students(self):
        """Refresh students list"""
        for item in self.students_tree.get_children():
            self.students_tree.delete(item)
        with self.db_lock:
            self.cursor.execute("SELECT id, name, roll_number, email, phone FROM students ORDER BY name")
            students = self.cursor.fetchall()
        for student in students:
            self.students_tree.insert('', 'end', values=student)
            
    def refresh_attendance(self):
        """Refresh today's attendance"""
        for item in self.attendance_tree.get_children():
            self.attendance_tree.delete(item)
        today = date.today()
        with self.db_lock:
            self.cursor.execute("""
                SELECT s.name, s.roll_number, a.time_in, a.status
                FROM attendance a
                JOIN students s ON a.student_id = s.id
                WHERE a.date = ?
                ORDER BY a.time_in
            """, (today,))
            attendance_records = self.cursor.fetchall()
        for record in attendance_records:
            self.attendance_tree.insert('', 'end', values=record)
            
    def generate_daily_report(self):
        """Generate daily attendance report"""
        from_date = self.from_date_entry.get()
        to_date = self.to_date_entry.get()
        # Clear previous report
        for item in self.report_tree.get_children():
            self.report_tree.delete(item)
        # Configure columns
        self.report_tree['columns'] = ('Date', 'Name', 'Roll', 'Time In', 'Status')
        for col in self.report_tree['columns']:
            self.report_tree.heading(col, text=col)
        # Get data
        with self.db_lock:
            self.cursor.execute("""
                SELECT a.date, s.name, s.roll_number, a.time_in, a.status
                FROM attendance a
                JOIN students s ON a.student_id = s.id
                WHERE a.date BETWEEN ? AND ?
                ORDER BY a.date, a.time_in
            """, (from_date, to_date))
            records = self.cursor.fetchall()
        for record in records:
            self.report_tree.insert('', 'end', values=record)
        self.logger.info(f"Generated daily report from {from_date} to {to_date}")
        
    def generate_student_report(self):
        """Generate student-wise attendance report"""
        from_date = self.from_date_entry.get()
        to_date = self.to_date_entry.get()
        # Clear previous report
        for item in self.report_tree.get_children():
            self.report_tree.delete(item)
        # Configure columns
        self.report_tree['columns'] = ('Name', 'Roll', 'Total Days', 'Present Days', 'Attendance %')
        for col in self.report_tree['columns']:
            self.report_tree.heading(col, text=col)
        # Get data
        with self.db_lock:
            self.cursor.execute("""
                SELECT s.name, s.roll_number, 
                       COUNT(DISTINCT a.date) as present_days,
                       (SELECT COUNT(DISTINCT date) FROM attendance WHERE date BETWEEN ? AND ?) as total_days
                FROM students s
                LEFT JOIN attendance a ON s.id = a.student_id AND a.date BETWEEN ? AND ?
                GROUP BY s.id, s.name, s.roll_number
                ORDER BY s.name
            """, (from_date, to_date, from_date, to_date))
            records = self.cursor.fetchall()
        for record in records:
            name, roll, present_days, total_days = record
            if total_days > 0:
                percentage = (present_days / total_days) * 100
            else:
                percentage = 0
            self.report_tree.insert('', 'end', values=(name, roll, total_days, present_days, f"{percentage:.1f}%"))
        self.logger.info(f"Generated student report from {from_date} to {to_date}")
        
    def export_to_excel(self):
        """Export current report to Excel"""
        try:
            # Get data from current report
            data = []
            columns = []
            if self.report_tree['columns']:
                columns = list(self.report_tree['columns'])
                for item in self.report_tree.get_children():
                    values = self.report_tree.item(item)['values']
                    data.append(values)
            if data:
                df = pd.DataFrame(data, columns=columns)
                # Save to Excel
                filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                filepath = os.path.join('reports', filename)
                df.to_excel(filepath, index=False)
                messagebox.showinfo("Success", f"Report exported to {filepath}")
                self.logger.info(f"Report exported to {filepath}")
            else:
                messagebox.showwarning("No Data", "There is no report data to export.")
                self.logger.warning("Export attempt with no data in report view")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export report: {str(e)}")
            self.logger.error(f"Export failed: {str(e)}")

    def backup_database(self):
        """Backup the database to the backup folder"""
        try:
            backup_path = os.path.join('backup', f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy2('database/attendance_system.db', backup_path)
            messagebox.showinfo("Success", f"Database backed up to {backup_path}")
            self.logger.info(f"Database backup created at {backup_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to backup database: {str(e)}")
            self.logger.error(f"Database backup failed: {str(e)}")

    def restore_database(self):
        """Restore the database from a selected backup file"""
        file_path = filedialog.askopenfilename(
            title="Select Backup File",
            filetypes=[("Database files", "*.db")]
        )
        if file_path:
            try:
                shutil.copy2(file_path, 'database/attendance_system.db')
                self.conn.close()
                self.setup_database()
                self.load_known_faces()
                self.refresh_students()
                self.refresh_attendance()
                messagebox.showinfo("Success", "Database restored successfully!")
                self.logger.info(f"Database restored from {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to restore database: {str(e)}")
                self.logger.error(f"Database restore failed: {str(e)}")

    def load_system_info(self):
        """Load and display system info in the settings tab"""
        info = {
            "System": "AI-Powered Attendance System",
            "Version": "1.0.0",
            "Database Path": os.path.abspath('database/attendance_system.db'),
            "Reports Directory": os.path.abspath('reports'),
            "Images Directory": os.path.abspath('student_images'),
            "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.info_text.delete('1.0', tk.END)
        self.info_text.insert(tk.END, json.dumps(info, indent=4))
        self.logger.info("System info loaded")

    def run(self):
        """Run the main application loop"""
        self.root.mainloop()


if __name__ == "__main__":
    app = AttendanceSystem()
    app.run()
