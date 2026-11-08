-- =====================================================================
--  SCHOOL MANAGEMENT SYSTEM  (PostgreSQL 9.2 compatible)
--  Roles: Admin, Faculty, Student
--  Run:  psql -U postgres -d your_db -f school_management_postgres.sql
-- =====================================================================
DROP SCHEMA IF EXISTS school CASCADE;
CREATE SCHEMA school;
SET search_path TO school;

-- =====================================================================
-- 1. SECURITY / USER MASTER
-- =====================================================================
CREATE TABLE roles (
    role_id      SERIAL PRIMARY KEY,
    role_name    VARCHAR(30) NOT NULL UNIQUE,          -- Admin / Faculty / Student
    description  VARCHAR(150)
);

CREATE TABLE users (                                    -- USER MASTER
    user_id        SERIAL PRIMARY KEY,
    role_id        INT NOT NULL REFERENCES roles(role_id),
    username       VARCHAR(50)  NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    first_name     VARCHAR(50)  NOT NULL,
    last_name      VARCHAR(50),
    email          VARCHAR(100) NOT NULL UNIQUE,
    phone          VARCHAR(15),
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    last_login     TIMESTAMP NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 2. ACADEMIC STRUCTURE
-- =====================================================================
CREATE TABLE academic_years (
    academic_year_id SERIAL PRIMARY KEY,
    year_name        VARCHAR(20) NOT NULL UNIQUE,       -- 2026-27
    start_date       DATE NOT NULL,
    end_date         DATE NOT NULL,
    is_current       BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (end_date > start_date)
);

CREATE TABLE classes (                                  -- Grade / Standard
    class_id    SERIAL PRIMARY KEY,
    class_name  VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE subjects (
    subject_id    SERIAL PRIMARY KEY,
    subject_code  VARCHAR(10) NOT NULL UNIQUE,
    subject_name  VARCHAR(80) NOT NULL,
    description   VARCHAR(200)
);

CREATE TABLE classrooms (
    classroom_id  SERIAL PRIMARY KEY,
    room_name     VARCHAR(30) NOT NULL UNIQUE,
    room_type     VARCHAR(15) NOT NULL DEFAULT 'Classroom'
                  CHECK (room_type IN ('Classroom','Lab','Library','Hall')),
    capacity      INT NOT NULL CHECK (capacity > 0)
);

-- =====================================================================
-- 3. PROFILES (one per user, depending on role)
-- =====================================================================
CREATE TABLE admins (
    admin_id     SERIAL PRIMARY KEY,
    user_id      INT NOT NULL UNIQUE REFERENCES users(user_id),
    designation  VARCHAR(50)
);

CREATE TABLE faculty (
    faculty_id     SERIAL PRIMARY KEY,
    user_id        INT NOT NULL UNIQUE REFERENCES users(user_id),
    employee_no    VARCHAR(20) NOT NULL UNIQUE,
    designation    VARCHAR(50),
    qualification  VARCHAR(100),
    joining_date   DATE
);

CREATE TABLE sections (                                 -- Grade 10 - A
    section_id         SERIAL PRIMARY KEY,
    class_id           INT NOT NULL REFERENCES classes(class_id),
    academic_year_id   INT NOT NULL REFERENCES academic_years(academic_year_id),
    section_name       VARCHAR(5) NOT NULL,
    class_teacher_id   INT NULL REFERENCES faculty(faculty_id),
    UNIQUE (class_id, academic_year_id, section_name)
);

CREATE TABLE students (
    student_id       SERIAL PRIMARY KEY,
    user_id          INT NOT NULL UNIQUE REFERENCES users(user_id),
    admission_no     VARCHAR(20) NOT NULL UNIQUE,
    roll_no          INT,
    section_id       INT NOT NULL REFERENCES sections(section_id),   -- current section
    date_of_birth    DATE,
    gender           VARCHAR(10) CHECK (gender IN ('Male','Female','Other')),
    guardian_name    VARCHAR(80),
    guardian_phone   VARCHAR(15),
    address          VARCHAR(200),
    admission_date   DATE
);

-- =====================================================================
-- 4. COURSE / SUBJECT ALLOCATION (course details + faculty assignments)
-- =====================================================================
CREATE TABLE course_assignments (   -- which faculty teaches which subject to which section, in which room
    assignment_id     SERIAL PRIMARY KEY,
    academic_year_id  INT NOT NULL REFERENCES academic_years(academic_year_id),
    section_id        INT NOT NULL REFERENCES sections(section_id),
    subject_id        INT NOT NULL REFERENCES subjects(subject_id),
    faculty_id        INT NOT NULL REFERENCES faculty(faculty_id),
    classroom_id      INT NOT NULL REFERENCES classrooms(classroom_id),
    periods_per_week  INT DEFAULT 5,
    UNIQUE (academic_year_id, section_id, subject_id)
);

-- =====================================================================
-- 5. TIMETABLE
-- =====================================================================
CREATE TABLE periods (
    period_id    SERIAL PRIMARY KEY,
    period_no    INT NOT NULL UNIQUE,
    start_time   TIME NOT NULL,
    end_time     TIME NOT NULL,
    CHECK (end_time > start_time)
);

CREATE TABLE timetable (
    timetable_id  SERIAL PRIMARY KEY,
    section_id    INT NOT NULL REFERENCES sections(section_id),
    day_of_week   VARCHAR(10) NOT NULL
                  CHECK (day_of_week IN ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')),
    period_id     INT NOT NULL REFERENCES periods(period_id),
    subject_id    INT NOT NULL REFERENCES subjects(subject_id),
    faculty_id    INT NOT NULL REFERENCES faculty(faculty_id),
    classroom_id  INT NOT NULL REFERENCES classrooms(classroom_id),
    UNIQUE (section_id,   day_of_week, period_id),      -- section can't have 2 classes at once
    UNIQUE (faculty_id,   day_of_week, period_id),      -- teacher can't be in 2 places
    UNIQUE (classroom_id, day_of_week, period_id)       -- room can't be double-booked
);

-- =====================================================================
-- 6. ATTENDANCE
-- =====================================================================
CREATE TABLE student_attendance (
    attendance_id    SERIAL PRIMARY KEY,
    student_id       INT NOT NULL REFERENCES students(student_id),
    attendance_date  DATE NOT NULL,
    period_id        INT NOT NULL REFERENCES periods(period_id),
    subject_id       INT NOT NULL REFERENCES subjects(subject_id),
    status           VARCHAR(10) NOT NULL CHECK (status IN ('Present','Absent','Late','Excused')),
    marked_by        INT NOT NULL REFERENCES faculty(faculty_id),
    remarks          VARCHAR(150),
    UNIQUE (student_id, attendance_date, period_id)
);

CREATE TABLE faculty_attendance (
    attendance_id    SERIAL PRIMARY KEY,
    faculty_id       INT NOT NULL REFERENCES faculty(faculty_id),
    attendance_date  DATE NOT NULL,
    check_in         TIME NULL,
    check_out        TIME NULL,
    status           VARCHAR(10) NOT NULL CHECK (status IN ('Present','Absent','Late','On Leave','Half Day')),
    UNIQUE (faculty_id, attendance_date)
);

-- =====================================================================
-- 7. LEAVE MANAGEMENT (students & faculty apply, admin approves)
-- =====================================================================
CREATE TABLE leave_types (
    leave_type_id  SERIAL PRIMARY KEY,
    type_name      VARCHAR(40) NOT NULL UNIQUE,
    max_days_year  INT
);

CREATE TABLE leave_requests (
    leave_id        SERIAL PRIMARY KEY,
    applicant_id    INT NOT NULL REFERENCES users(user_id),        -- student or faculty user
    leave_type_id   INT NOT NULL REFERENCES leave_types(leave_type_id),
    from_date       DATE NOT NULL,
    to_date         DATE NOT NULL,
    reason          VARCHAR(255),
    status          VARCHAR(10) NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Approved','Rejected')),
    applied_on      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by     INT NULL REFERENCES users(user_id),            -- admin user
    reviewed_on     TIMESTAMP NULL,
    admin_remarks   VARCHAR(255),
    CHECK (to_date >= from_date)
);

-- =====================================================================
-- 8. HOMEWORK
-- =====================================================================
CREATE TABLE homework (
    homework_id    SERIAL PRIMARY KEY,
    section_id     INT NOT NULL REFERENCES sections(section_id),
    subject_id     INT NOT NULL REFERENCES subjects(subject_id),
    faculty_id     INT NOT NULL REFERENCES faculty(faculty_id),
    title          VARCHAR(150) NOT NULL,
    description    TEXT,
    assigned_date  DATE NOT NULL,
    due_date       DATE NOT NULL,
    CHECK (due_date >= assigned_date)
);

CREATE TABLE homework_submissions (
    submission_id   SERIAL PRIMARY KEY,
    homework_id     INT NOT NULL REFERENCES homework(homework_id),
    student_id      INT NOT NULL REFERENCES students(student_id),
    submitted_on    TIMESTAMP NULL,
    file_path       VARCHAR(255),
    status          VARCHAR(10) NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Submitted','Late','Checked')),
    faculty_remarks VARCHAR(255),
    UNIQUE (homework_id, student_id)
);

-- =====================================================================
-- 9. ASSIGNMENTS (graded work / projects)
-- =====================================================================
CREATE TABLE assignments (
    assignment_id  SERIAL PRIMARY KEY,
    section_id     INT NOT NULL REFERENCES sections(section_id),
    subject_id     INT NOT NULL REFERENCES subjects(subject_id),
    faculty_id     INT NOT NULL REFERENCES faculty(faculty_id),
    title          VARCHAR(150) NOT NULL,
    description    TEXT,
    max_marks      NUMERIC(5,2) NOT NULL,
    assigned_date  DATE NOT NULL,
    due_date       DATE NOT NULL,
    CHECK (due_date >= assigned_date)
);

CREATE TABLE assignment_submissions (
    submission_id   SERIAL PRIMARY KEY,
    assignment_id   INT NOT NULL REFERENCES assignments(assignment_id),
    student_id      INT NOT NULL REFERENCES students(student_id),
    submitted_on    TIMESTAMP NULL,
    file_path       VARCHAR(255),
    marks_obtained  NUMERIC(5,2) NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Submitted','Late','Graded')),
    feedback        VARCHAR(255),
    UNIQUE (assignment_id, student_id)
);

-- =====================================================================
-- 10. EXAMS & MARKS
-- =====================================================================
CREATE TABLE exam_types (
    exam_type_id  SERIAL PRIMARY KEY,
    type_name     VARCHAR(40) NOT NULL UNIQUE,          -- Unit Test, Mid Term, Final
    weightage     NUMERIC(5,2)
);

CREATE TABLE exams (
    exam_id           SERIAL PRIMARY KEY,
    academic_year_id  INT NOT NULL REFERENCES academic_years(academic_year_id),
    exam_type_id      INT NOT NULL REFERENCES exam_types(exam_type_id),
    class_id          INT NOT NULL REFERENCES classes(class_id),
    exam_name         VARCHAR(100) NOT NULL,
    start_date        DATE,
    end_date          DATE,
    created_by        INT NOT NULL REFERENCES users(user_id)       -- admin user
);

CREATE TABLE exam_schedules (
    exam_schedule_id  SERIAL PRIMARY KEY,
    exam_id           INT NOT NULL REFERENCES exams(exam_id),
    subject_id        INT NOT NULL REFERENCES subjects(subject_id),
    exam_date         DATE NOT NULL,
    start_time        TIME NOT NULL,
    end_time          TIME NOT NULL,
    classroom_id      INT NOT NULL REFERENCES classrooms(classroom_id),
    invigilator_id    INT NULL REFERENCES faculty(faculty_id),
    max_marks         NUMERIC(5,2) NOT NULL,
    pass_marks        NUMERIC(5,2) NOT NULL,
    UNIQUE (exam_id, subject_id),
    CHECK (pass_marks <= max_marks)
);

CREATE TABLE grade_scale (
    grade_id     SERIAL PRIMARY KEY,
    grade        VARCHAR(3) NOT NULL UNIQUE,
    min_percent  NUMERIC(5,2) NOT NULL,
    max_percent  NUMERIC(5,2) NOT NULL,
    grade_point  NUMERIC(3,1),
    remark       VARCHAR(40)
);

CREATE TABLE marks (
    mark_id           SERIAL PRIMARY KEY,
    exam_schedule_id  INT NOT NULL REFERENCES exam_schedules(exam_schedule_id),
    student_id        INT NOT NULL REFERENCES students(student_id),
    marks_obtained    NUMERIC(5,2) NULL,
    is_absent         BOOLEAN NOT NULL DEFAULT FALSE,
    grade_id          INT NULL REFERENCES grade_scale(grade_id),
    entered_by        INT NOT NULL REFERENCES faculty(faculty_id),
    entered_on        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    remarks           VARCHAR(150),
    UNIQUE (exam_schedule_id, student_id)
);

-- =====================================================================
-- 11. PROGRESS REPORT
-- =====================================================================
CREATE TABLE progress_reports (
    report_id         SERIAL PRIMARY KEY,
    student_id        INT NOT NULL REFERENCES students(student_id),
    exam_id           INT NOT NULL REFERENCES exams(exam_id),
    total_max_marks   NUMERIC(7,2),
    total_obtained    NUMERIC(7,2),
    percentage        NUMERIC(5,2),
    grade_id          INT REFERENCES grade_scale(grade_id),
    attendance_pct    NUMERIC(5,2),
    class_rank        INT,
    teacher_remarks   VARCHAR(255),
    generated_by      INT NOT NULL REFERENCES users(user_id),      -- admin / class teacher
    generated_on      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_published      BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (student_id, exam_id)
);

CREATE TABLE progress_report_items (
    item_id         SERIAL PRIMARY KEY,
    report_id       INT NOT NULL REFERENCES progress_reports(report_id),
    subject_id      INT NOT NULL REFERENCES subjects(subject_id),
    max_marks       NUMERIC(5,2),
    marks_obtained  NUMERIC(5,2),
    grade_id        INT REFERENCES grade_scale(grade_id),
    UNIQUE (report_id, subject_id)
);

-- =====================================================================
-- 12. NOTIFICATIONS
-- =====================================================================
CREATE TABLE notifications (
    notification_id  SERIAL PRIMARY KEY,
    user_id          INT NOT NULL REFERENCES users(user_id),
    title            VARCHAR(100) NOT NULL,
    message          VARCHAR(255),
    is_read          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- INDEXES on foreign keys (PostgreSQL does not create these automatically)
-- =====================================================================
CREATE INDEX idx_users_role            ON users(role_id);
CREATE INDEX idx_students_section      ON students(section_id);
CREATE INDEX idx_sections_class        ON sections(class_id);
CREATE INDEX idx_sections_teacher      ON sections(class_teacher_id);
CREATE INDEX idx_course_asg_faculty    ON course_assignments(faculty_id);
CREATE INDEX idx_timetable_subject     ON timetable(subject_id);
CREATE INDEX idx_stu_att_date          ON student_attendance(attendance_date);
CREATE INDEX idx_stu_att_student       ON student_attendance(student_id);
CREATE INDEX idx_fac_att_date          ON faculty_attendance(attendance_date);
CREATE INDEX idx_leave_applicant       ON leave_requests(applicant_id);
CREATE INDEX idx_leave_status          ON leave_requests(status);
CREATE INDEX idx_homework_section      ON homework(section_id);
CREATE INDEX idx_hw_sub_student        ON homework_submissions(student_id);
CREATE INDEX idx_assignments_section   ON assignments(section_id);
CREATE INDEX idx_asg_sub_student       ON assignment_submissions(student_id);
CREATE INDEX idx_exams_class           ON exams(class_id);
CREATE INDEX idx_marks_student         ON marks(student_id);
CREATE INDEX idx_reports_exam          ON progress_reports(exam_id);
CREATE INDEX idx_notif_user            ON notifications(user_id, is_read);

-- #####################################################################
--                           SAMPLE DATA
-- #####################################################################

INSERT INTO roles (role_name, description) VALUES
('Admin',   'School administrator - full reporting and approval rights'),
('Faculty', 'Teaching staff'),
('Student', 'Enrolled student');

-- password_hash values are placeholders (use bcrypt/argon2 in a real application)
INSERT INTO users (role_id, username, password_hash, first_name, last_name, email, phone) VALUES
(1, 'admin01',   '$2b$10$hash_admin',  'Ramesh', 'Kumar',  'admin@school.edu',         '9000000001'),  -- 1
(2, 'fac_anita', '$2b$10$hash_anita',  'Anita',  'Sharma', 'anita@school.edu',         '9000000002'),  -- 2
(2, 'fac_vijay', '$2b$10$hash_vijay',  'Vijay',  'Reddy',  'vijay@school.edu',         '9000000003'),  -- 3
(2, 'fac_sara',  '$2b$10$hash_sara',   'Sara',   'Thomas', 'sara@school.edu',          '9000000004'),  -- 4
(3, 'stu_arjun', '$2b$10$hash_arjun',  'Arjun',  'Rao',    'arjun@student.school.edu', '9100000001'),  -- 5
(3, 'stu_meera', '$2b$10$hash_meera',  'Meera',  'Iyer',   'meera@student.school.edu', '9100000002'),  -- 6
(3, 'stu_kiran', '$2b$10$hash_kiran',  'Kiran',  'Patel',  'kiran@student.school.edu', '9100000003'),  -- 7
(3, 'stu_divya', '$2b$10$hash_divya',  'Divya',  'Nair',   'divya@student.school.edu', '9100000004');  -- 8

INSERT INTO academic_years (year_name, start_date, end_date, is_current) VALUES
('2026-27', '2026-06-01', '2027-04-30', TRUE);

INSERT INTO classes (class_name) VALUES ('Grade 9'), ('Grade 10');

INSERT INTO subjects (subject_code, subject_name, description) VALUES
('MATH', 'Mathematics', 'Algebra, Geometry, Trigonometry'),
('SCI',  'Science',     'Physics, Chemistry, Biology'),
('ENG',  'English',     'Language and Literature');

INSERT INTO classrooms (room_name, room_type, capacity) VALUES
('Room 101',    'Classroom', 40),
('Room 102',    'Classroom', 40),
('Science Lab', 'Lab',       30);

INSERT INTO admins (user_id, designation) VALUES (1, 'Principal');

INSERT INTO faculty (user_id, employee_no, designation, qualification, joining_date) VALUES
(2, 'EMP001', 'Senior Teacher', 'M.Sc Mathematics, B.Ed', '2015-06-10'),
(3, 'EMP002', 'Teacher',        'M.Sc Physics, B.Ed',     '2018-06-12'),
(4, 'EMP003', 'Teacher',        'M.A English, B.Ed',      '2020-07-01');

INSERT INTO sections (class_id, academic_year_id, section_name, class_teacher_id) VALUES
(1, 1, 'A', 1),   -- section 1: Grade 9-A
(2, 1, 'A', 2);   -- section 2: Grade 10-A

INSERT INTO students (user_id, admission_no, roll_no, section_id, date_of_birth, gender, guardian_name, guardian_phone, address, admission_date) VALUES
(5, 'ADM2026001', 1, 1, '2011-03-14', 'Male',   'Suresh Rao',   '9200000001', 'Hyderabad', '2026-06-01'),
(6, 'ADM2026002', 2, 1, '2011-08-22', 'Female', 'Lakshmi Iyer', '9200000002', 'Hyderabad', '2026-06-01'),
(7, 'ADM2025003', 1, 2, '2010-01-05', 'Male',   'Manoj Patel',  '9200000003', 'Hyderabad', '2025-06-01'),
(8, 'ADM2025004', 2, 2, '2010-11-30', 'Female', 'Gopal Nair',   '9200000004', 'Hyderabad', '2025-06-01');

INSERT INTO course_assignments (academic_year_id, section_id, subject_id, faculty_id, classroom_id, periods_per_week) VALUES
(1, 1, 1, 1, 1, 6),
(1, 1, 2, 2, 3, 5),
(1, 1, 3, 3, 1, 5),
(1, 2, 1, 1, 2, 6),
(1, 2, 2, 2, 3, 5),
(1, 2, 3, 3, 2, 5);

INSERT INTO periods (period_no, start_time, end_time) VALUES
(1, '08:30', '09:15'),
(2, '09:15', '10:00'),
(3, '10:15', '11:00');

INSERT INTO timetable (section_id, day_of_week, period_id, subject_id, faculty_id, classroom_id) VALUES
-- Grade 9-A Monday
(1, 'Monday',  1, 1, 1, 1),
(1, 'Monday',  2, 2, 2, 3),
(1, 'Monday',  3, 3, 3, 1),
-- Grade 10-A Monday
(2, 'Monday',  1, 3, 3, 2),
(2, 'Monday',  2, 1, 1, 2),
(2, 'Monday',  3, 2, 2, 3),
-- Grade 9-A Tuesday
(1, 'Tuesday', 1, 2, 2, 3),
(1, 'Tuesday', 2, 3, 3, 1);

INSERT INTO student_attendance (student_id, attendance_date, period_id, subject_id, status, marked_by, remarks) VALUES
(1, '2026-11-02', 1, 1, 'Present', 1, NULL),
(2, '2026-11-02', 1, 1, 'Absent',  1, 'Fever'),
(3, '2026-11-02', 1, 3, 'Present', 3, NULL),
(4, '2026-11-02', 1, 3, 'Late',    3, 'Bus delay'),
(1, '2026-11-02', 2, 2, 'Present', 2, NULL),
(2, '2026-11-02', 2, 2, 'Absent',  2, 'Fever'),
(3, '2026-11-02', 2, 1, 'Present', 1, NULL),
(4, '2026-11-02', 2, 1, 'Present', 1, NULL);

INSERT INTO faculty_attendance (faculty_id, attendance_date, check_in, check_out, status) VALUES
(1, '2026-11-02', '08:15', '16:00', 'Present'),
(2, '2026-11-02', '08:40', '16:05', 'Late'),
(3, '2026-11-02', NULL,    NULL,    'On Leave');

INSERT INTO leave_types (type_name, max_days_year) VALUES
('Sick Leave', 12), ('Casual Leave', 10), ('Earned Leave', 15);

INSERT INTO leave_requests (applicant_id, leave_type_id, from_date, to_date, reason, status, reviewed_by, reviewed_on, admin_remarks) VALUES
(4, 1, '2026-11-02', '2026-11-03', 'Viral fever',          'Approved', 1,    '2026-11-01 17:00', 'Get well soon'),
(6, 1, '2026-11-02', '2026-11-04', 'Fever, doctor advice', 'Pending',  NULL, NULL,               NULL),
(2, 2, '2026-11-10', '2026-11-10', 'Family function',      'Rejected', 1,    '2026-11-03 09:00', 'Exams in progress');

INSERT INTO homework (section_id, subject_id, faculty_id, title, description, assigned_date, due_date) VALUES
(1, 1, 1, 'Algebra Worksheet 5',  'Solve questions 1-20 from worksheet 5', '2026-11-02', '2026-11-05'),
(2, 3, 3, 'Essay: My Role Model', 'Write a 300 word essay',                '2026-11-02', '2026-11-06');

INSERT INTO homework_submissions (homework_id, student_id, submitted_on, file_path, status, faculty_remarks) VALUES
(1, 1, '2026-11-03 18:00', '/uploads/hw/arjun_alg5.pdf',  'Checked',   'Good work'),
(1, 2, NULL,               NULL,                          'Pending',   NULL),
(2, 3, '2026-11-03 20:10', '/uploads/hw/kiran_essay.pdf', 'Submitted', NULL),
(2, 4, NULL,               NULL,                          'Pending',   NULL);

INSERT INTO assignments (section_id, subject_id, faculty_id, title, description, max_marks, assigned_date, due_date) VALUES
(2, 2, 2, 'Science Project: Solar Energy', 'Working model with report', 20, '2026-10-20', '2026-11-15'),
(1, 1, 1, 'Geometry Assignment 1',         'Constructions and proofs',  10, '2026-10-25', '2026-11-08');

INSERT INTO assignment_submissions (assignment_id, student_id, submitted_on, file_path, marks_obtained, status, feedback) VALUES
(1, 3, '2026-11-01 10:00', '/uploads/asg/kiran_solar.pdf', 17.00, 'Graded',  'Excellent model'),
(1, 4, NULL,               NULL,                           NULL,  'Pending', NULL),
(2, 1, '2026-11-02 15:30', '/uploads/asg/arjun_geo.pdf',   8.50,  'Graded',  'Neat constructions'),
(2, 2, NULL,               NULL,                           NULL,  'Pending', NULL);

INSERT INTO exam_types (type_name, weightage) VALUES
('Unit Test', 20.00), ('Mid Term', 30.00), ('Final Exam', 50.00);

INSERT INTO exams (academic_year_id, exam_type_id, class_id, exam_name, start_date, end_date, created_by) VALUES
(1, 2, 2, 'Grade 10 Mid Term 2026', '2026-10-12', '2026-10-16', 1);

INSERT INTO exam_schedules (exam_id, subject_id, exam_date, start_time, end_time, classroom_id, invigilator_id, max_marks, pass_marks) VALUES
(1, 1, '2026-10-12', '09:00', '12:00', 2, 2, 100, 35),
(1, 2, '2026-10-14', '09:00', '12:00', 2, 3, 100, 35),
(1, 3, '2026-10-16', '09:00', '12:00', 2, 1, 100, 35);

INSERT INTO grade_scale (grade, min_percent, max_percent, grade_point, remark) VALUES
('A+', 90.00, 100.00, 10.0, 'Outstanding'),   -- 1
('A',  80.00,  89.99,  9.0, 'Excellent'),     -- 2
('B+', 70.00,  79.99,  8.0, 'Very Good'),     -- 3
('B',  60.00,  69.99,  7.0, 'Good'),          -- 4
('C',  50.00,  59.99,  6.0, 'Average'),       -- 5
('F',   0.00,  49.99,  0.0, 'Fail');          -- 6

INSERT INTO marks (exam_schedule_id, student_id, marks_obtained, is_absent, grade_id, entered_by, remarks) VALUES
(1, 3, 88, FALSE, 2, 1, NULL),
(2, 3, 76, FALSE, 3, 2, NULL),
(3, 3, 82, FALSE, 2, 3, NULL),
(1, 4, 95, FALSE, 1, 1, 'Top scorer'),
(2, 4, 91, FALSE, 1, 2, NULL),
(3, 4, 89, FALSE, 2, 3, NULL);

INSERT INTO progress_reports (student_id, exam_id, total_max_marks, total_obtained, percentage, grade_id, attendance_pct, class_rank, teacher_remarks, generated_by, is_published) VALUES
(3, 1, 300, 246, 82.00, 2, 90.00, 2, 'Good performance, improve Science', 1, TRUE),
(4, 1, 300, 275, 91.67, 1, 96.50, 1, 'Outstanding, keep it up',           1, TRUE);

INSERT INTO progress_report_items (report_id, subject_id, max_marks, marks_obtained, grade_id) VALUES
(1, 1, 100, 88, 2), (1, 2, 100, 76, 3), (1, 3, 100, 82, 2),
(2, 1, 100, 95, 1), (2, 2, 100, 91, 1), (2, 3, 100, 89, 2);

INSERT INTO notifications (user_id, title, message) VALUES
(5, 'New Homework',      'Algebra Worksheet 5 due on 05-Nov'),
(7, 'Progress Report',   'Your Mid Term progress report is published'),
(1, 'Leave Request',     'Meera Iyer has applied for sick leave'),
(2, 'Timetable Updated', 'Your Monday timetable has been updated');

-- #####################################################################
--  VIEWS FOR ADMIN REPORTS
-- #####################################################################

-- Student attendance % report
CREATE VIEW v_student_attendance_report AS
SELECT s.student_id, s.admission_no,
       u.first_name || ' ' || COALESCE(u.last_name, '') AS student_name,
       c.class_name, sec.section_name,
       COUNT(*) AS total_periods,
       SUM(CASE WHEN sa.status IN ('Present','Late') THEN 1 ELSE 0 END) AS attended,
       ROUND(100.0 * SUM(CASE WHEN sa.status IN ('Present','Late') THEN 1 ELSE 0 END) / COUNT(*), 2) AS attendance_pct
FROM student_attendance sa
JOIN students s   ON s.student_id  = sa.student_id
JOIN users u      ON u.user_id     = s.user_id
JOIN sections sec ON sec.section_id = s.section_id
JOIN classes c    ON c.class_id    = sec.class_id
GROUP BY s.student_id, s.admission_no, u.first_name, u.last_name, c.class_name, sec.section_name;

-- Exam result report (subject-wise)
CREATE VIEW v_exam_report AS
SELECT e.exam_name,
       u.first_name || ' ' || COALESCE(u.last_name, '') AS student_name,
       sub.subject_name, es.max_marks, m.marks_obtained,
       CASE WHEN m.marks_obtained >= es.pass_marks THEN 'Pass' ELSE 'Fail' END AS result,
       g.grade
FROM marks m
JOIN exam_schedules es ON es.exam_schedule_id = m.exam_schedule_id
JOIN exams e           ON e.exam_id    = es.exam_id
JOIN subjects sub      ON sub.subject_id = es.subject_id
JOIN students s        ON s.student_id = m.student_id
JOIN users u           ON u.user_id    = s.user_id
LEFT JOIN grade_scale g ON g.grade_id  = m.grade_id;

-- Pending leave approvals for admin
CREATE VIEW v_pending_leaves AS
SELECT lr.leave_id,
       u.first_name || ' ' || COALESCE(u.last_name, '') AS applicant,
       r.role_name, lt.type_name, lr.from_date, lr.to_date, lr.reason
FROM leave_requests lr
JOIN users u        ON u.user_id = lr.applicant_id
JOIN roles r        ON r.role_id = u.role_id
JOIN leave_types lt ON lt.leave_type_id = lr.leave_type_id
WHERE lr.status = 'Pending';

-- Weekly timetable for a section (admin / faculty / student view)
CREATE VIEW v_timetable AS
SELECT sec.section_id, c.class_name || '-' || sec.section_name AS section,
       t.day_of_week, p.period_no, p.start_time, p.end_time,
       sub.subject_name,
       u.first_name || ' ' || COALESCE(u.last_name, '') AS faculty_name,
       cr.room_name
FROM timetable t
JOIN sections sec  ON sec.section_id  = t.section_id
JOIN classes c     ON c.class_id      = sec.class_id
JOIN periods p     ON p.period_id     = t.period_id
JOIN subjects sub  ON sub.subject_id  = t.subject_id
JOIN faculty f     ON f.faculty_id    = t.faculty_id
JOIN users u       ON u.user_id       = f.user_id
JOIN classrooms cr ON cr.classroom_id = t.classroom_id;

-- Sample queries
-- SELECT * FROM school.v_student_attendance_report;
-- SELECT * FROM school.v_exam_report;
-- SELECT * FROM school.v_pending_leaves;
-- SELECT * FROM school.v_timetable WHERE section = 'Grade 10-A' ORDER BY day_of_week, period_no;
