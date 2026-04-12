from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
import os
import re
from collections import Counter
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from datetime import datetime
import PyPDF2
import docx
from fpdf import FPDF
import unicodedata

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('wordnet')

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OPTIMIZED_FOLDER'] = 'optimized_resumes'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OPTIMIZED_FOLDER'], exist_ok=True)

def clean_unicode_text(text):
    """Replace Unicode characters with ASCII equivalents"""
    # Replace common Unicode characters
    replacements = {
        '–': '-',     # en dash
        '—': '-',     # em dash
        '•': '-',     # bullet
        '·': '-',     # middle dot
        '◦': '-',     # white bullet
        '…': '...',   # ellipsis
        '‘': "'",     # left single quote
        '’': "'",     # right single quote
        '“': '"',     # left double quote
        '”': '"',     # right double quote
        '©': '(c)',   # copyright
        '®': '(r)',   # registered
        '™': '(tm)',  # trademark
        '€': 'EUR',   # euro
        '£': 'GBP',   # pound
        '¥': 'JPY',   # yen
        '°': ' deg',  # degree
        '→': '->',    # arrow
        '←': '<-',    # arrow
        '↑': '^',     # arrow
        '↓': 'v',     # arrow
    }
    
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    
    # Remove any other non-ASCII characters
    text = ''.join(char if ord(char) < 128 else ' ' for char in text)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text

class ResumeMatcher:
    def __init__(self):
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
    
    def extract_text_from_pdf(self, file):
        """Extract text from PDF"""
        text = ""
        try:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        except Exception as e:
            print(f"Error: {e}")
        return text
    
    def extract_text_from_docx(self, file):
        """Extract text from DOCX"""
        text = ""
        try:
            doc = docx.Document(file)
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text += paragraph.text + "\n"
        except Exception as e:
            print(f"Error: {e}")
        return text
    
    def extract_text_from_txt(self, file):
        """Extract text from TXT"""
        try:
            text = file.read().decode('utf-8')
            return text
        except:
            try:
                file.seek(0)
                return file.read().decode('latin-1')
            except:
                return ""
    
    def read_file(self, file, filename):
        """Read text from various file formats"""
        if filename.endswith('.pdf'):
            return self.extract_text_from_pdf(file)
        elif filename.endswith('.docx'):
            return self.extract_text_from_docx(file)
        else:
            return self.extract_text_from_txt(file)
    
    def preprocess_text(self, text):
        """Clean and preprocess text for keyword matching"""
        text = text.lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        words = word_tokenize(text)
        words = [self.lemmatizer.lemmatize(word) for word in words 
                if word not in self.stop_words and len(word) > 2]
        return words
    
    def calculate_match_score(self, resume_text, job_text):
        """Calculate match percentage"""
        resume_keywords = set(self.preprocess_text(resume_text))
        job_keywords = set(self.preprocess_text(job_text))
        
        if not job_keywords:
            return 0, set(), set()
        
        matches = resume_keywords.intersection(job_keywords)
        match_percentage = (len(matches) / len(job_keywords)) * 100
        
        return match_percentage, matches, job_keywords - resume_keywords
    
    def extract_name_from_resume(self, text):
        """Extract name from resume"""
        lines = text.split('\n')[:10]
        for line in lines:
            line = line.strip()
            if line and len(line.split()) <= 3:
                words = line.split()
                if all(word[0].isupper() and word.isalpha() for word in words):
                    return line.replace(' ', '_')
        return "Candidate"
    
    def extract_job_role(self, text):
        """Extract job role from job description"""
        lines = text.split('\n')[:20]
        for line in lines:
            line = line.strip()
            job_patterns = ['Engineer', 'Developer', 'Manager', 'Analyst', 'Designer', 
                          'Architect', 'Consultant', 'Specialist', 'Director']
            for pattern in job_patterns:
                if pattern in line:
                    words = line.split()
                    for i, word in enumerate(words):
                        if pattern in word:
                            if i > 0:
                                return f"{words[i-1]}_{words[i]}".replace('/', '_').replace(' ', '_')
                            return words[i].replace('/', '_')
        return "Job_Role"
    
    def generate_filename(self, resume_text, job_text):
        """Generate filename: Name_JobRole.pdf"""
        name = self.extract_name_from_resume(resume_text)
        job_role = self.extract_job_role(job_text)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{name}_{job_role}_{timestamp}.pdf"
    
    def update_resume_with_keywords(self, original_text, missing_keywords):
        """Add missing keywords to skills section without changing format"""
        if not missing_keywords:
            return original_text
        
        keywords_to_add = ', '.join([kw.capitalize() for kw in list(missing_keywords)[:15]])
        
        lines = original_text.split('\n')
        updated_lines = []
        skills_found = False
        
        for i, line in enumerate(lines):
            updated_lines.append(line)
            
            if 'skill' in line.lower() or 'SKILL' in line:
                skills_found = True
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        updated_lines[-1] = f"{parts[0]}: {parts[1].strip()}, {keywords_to_add}"
                    else:
                        updated_lines[-1] = f"{line}, {keywords_to_add}"
                else:
                    updated_lines.append(f"  {keywords_to_add}")
        
        if not skills_found:
            insert_position = 3
            updated_lines.insert(insert_position, f"\nSKILLS\n{keywords_to_add}\n")
        
        return '\n'.join(updated_lines)
    
    def create_pdf_from_text(self, text, output_path):
        """Create PDF with clean ASCII text"""
        # Clean all Unicode characters from text
        clean_text = clean_unicode_text(text)
        
        # Create PDF
        pdf = FPDF('P', 'mm', 'A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=25)
        
        # Set margins
        pdf.set_left_margin(20)
        pdf.set_right_margin(20)
        pdf.set_top_margin(20)
        
        # Use standard font
        pdf.set_font("helvetica", size=11)
        
        # Split text into lines
        lines = clean_text.split('\n')
        
        for line in lines:
            if line.strip():
                # Check if it's a heading (all caps or short)
                if line.isupper() and len(line) < 60:
                    pdf.set_font("helvetica", 'B', 13)
                    pdf.multi_cell(170, 8, line, 0, 'L')
                    pdf.set_font("helvetica", size=11)
                    pdf.ln(2)
                else:
                    # Check if it's a bullet point
                    if line.strip().startswith('-'):
                        pdf.set_x(25)
                        pdf.multi_cell(165, 6, line, 0, 'L')
                    else:
                        pdf.multi_cell(170, 6, line, 0, 'L')
            else:
                pdf.ln(4)
        
        # Save PDF
        pdf.output(output_path)
    
    def analyze(self, resume_text, job_text):
        """Main analysis function"""
        # Clean resume text first
        resume_text = clean_unicode_text(resume_text)
        job_text = clean_unicode_text(job_text)
        
        # Calculate match score
        match_score, matching_keywords, missing_keywords = self.calculate_match_score(resume_text, job_text)
        
        # Update resume with missing keywords
        updated_resume = self.update_resume_with_keywords(resume_text, missing_keywords)
        
        # Clean again after updates
        updated_resume = clean_unicode_text(updated_resume)
        
        # Generate filename
        filename = self.generate_filename(resume_text, job_text)
        pdf_path = os.path.join(app.config['OPTIMIZED_FOLDER'], filename)
        
        # Create PDF
        self.create_pdf_from_text(updated_resume, pdf_path)
        
        # Extract info for display
        name = self.extract_name_from_resume(resume_text).replace('_', ' ')
        job_role = self.extract_job_role(job_text).replace('_', ' ')
        
        return {
            'match_score': round(match_score, 1),
            'matching_keywords': list(matching_keywords)[:20],
            'missing_keywords': list(missing_keywords)[:20],
            'total_matching': len(matching_keywords),
            'total_missing': len(missing_keywords),
            'verdict': 'good' if match_score >= 70 else 'moderate' if match_score >= 50 else 'poor',
            'filename': filename,
            'name': name,
            'job_role': job_role,
            'improvement': round(len(missing_keywords) * 2, 1)
        }

matcher = ResumeMatcher()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        resume_file = request.files.get('resume')
        job_file = request.files.get('job_description')
        
        if not resume_file or not job_file:
            return jsonify({'error': 'Please upload both files'}), 400
        
        resume_filename = secure_filename(resume_file.filename)
        job_filename = secure_filename(job_file.filename)
        
        resume_text = matcher.read_file(resume_file, resume_filename)
        job_text = matcher.read_file(job_file, job_filename)
        
        if not resume_text:
            return jsonify({'error': 'Could not extract text from resume'}), 400
        
        results = matcher.analyze(resume_text, job_text)
        
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['OPTIMIZED_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 RESUME OPTIMIZER - UNICODE FIXED")
    print("="*70)
    print("\n✅ Server started at: http://localhost:5000")
    print("📁 Upload your resume and job description")
    print("🔤 All special characters converted to ASCII")
    print("📥 Downloads as: YourName_JobRole_Timestamp.pdf")
    print("\n⚠️  Press CTRL+C to stop\n")
    app.run(debug=True, host='127.0.0.1', port=5000)