from flask import Flask, request, jsonify, render_template_string, send_file
import os
import re
from collections import Counter
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('wordnet')

app = Flask(__name__)
app.config['OPTIMIZED_FOLDER'] = 'optimized_resumes'
os.makedirs(app.config['OPTIMIZED_FOLDER'], exist_ok=True)

class ResumeMatcher:
    def __init__(self):
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
    
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
        """Extract name from first line"""
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 50 and not any(x in line.lower() for x in ['@', 'linkedin', 'github']):
                return line
        return "Resume"
    
    def extract_contact_info(self, text):
        """Extract contact info lines"""
        lines = text.strip().split('\n')
        for line in lines:
            if '@' in line or 'linkedin' in line.lower() or 'github' in line.lower():
                return line.strip()
        return ""
    
    def extract_job_role(self, text):
        """Extract job role"""
        lines = text.split('\n')[:20]
        for line in lines:
            for pattern in ['Engineer', 'Developer', 'Manager', 'Analyst', 'DevOps', 'Software']:
                if pattern in line:
                    return pattern
        return "Position"
    
    def generate_filename(self, resume_text, job_text):
        """Generate filename"""
        name = self.extract_name_from_resume(resume_text).replace(' ', '_')
        job_role = self.extract_job_role(job_text)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{name}_{job_role}_{timestamp}.docx"
    
    def add_missing_keywords(self, resume_text, missing_keywords):
        """Add missing keywords to skills section"""
        if not missing_keywords:
            return resume_text
        
        keywords_to_add = ', '.join([kw.capitalize() for kw in list(missing_keywords)[:10]])
        
        lines = resume_text.split('\n')
        new_lines = []
        added = False
        
        for line in lines:
            new_lines.append(line)
            if not added and ('CORE SKILLS' in line or 'SKILLS' in line):
                new_lines.append(f"  {keywords_to_add}")
                added = True
        
        if not added:
            new_lines.insert(3, f"\nSKILLS\n{keywords_to_add}\n")
        
        return '\n'.join(new_lines)
    
    def create_beautiful_word(self, text, output_path):
        """Create beautifully formatted Word document"""
        doc = Document()
        
        # Set page margins
        for section in doc.sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)
        
        lines = text.split('\n')
        
        # Track if we've added name and contact
        name_added = False
        contact_added = False
        
        for line in lines:
            line = line.strip()
            if not line:
                doc.add_paragraph()
                continue
            
            # Check if this is the name line (first meaningful line)
            if not name_added and len(line) < 50 and not any(x in line.lower() for x in ['@', 'linkedin', 'github', '|']):
                # Add centered name
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(line)
                run.font.name = 'Calibri'
                run.font.size = Pt(24)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0, 0, 0)
                name_added = True
                continue
            
            # Check if this is contact info
            if not contact_added and ('@' in line or 'linkedin' in line.lower() or 'github' in line.lower()):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(line)
                run.font.name = 'Calibri'
                run.font.size = Pt(10)
                run.font.italic = True
                run.font.color.rgb = RGBColor(100, 100, 100)
                contact_added = True
                continue
            
            # Check if it's a section header (all caps)
            if line.isupper() and len(line) < 50:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(6)
                run = p.add_run(line)
                run.font.name = 'Calibri'
                run.font.size = Pt(16)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0, 51, 102)
                # Add underline
                run.font.underline = True
                continue
            
            # Check if it's a company/subheader
            if '|' in line or ' at ' in line.lower():
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(8)
                p.paragraph_format.space_after = Pt(4)
                run = p.add_run(line)
                run.font.name = 'Calibri'
                run.font.size = Pt(12)
                run.font.bold = True
                run.font.color.rgb = RGBColor(64, 64, 64)
                continue
            
            # Check if it's a bullet point
            if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.25)
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                bullet_text = line[1:].strip()
                run = p.add_run(f"• {bullet_text}")
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
                continue
            
            # Check if it's a skill category (contains :)
            if ':' in line and len(line.split(':')) == 2:
                parts = line.split(':', 1)
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after = Pt(2)
                run = p.add_run(parts[0] + ': ')
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
                run.font.bold = True
                run = p.add_run(parts[1].strip())
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
                continue
            
            # Regular paragraph text
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            run = p.add_run(line)
            run.font.name = 'Calibri'
            run.font.size = Pt(11)
        
        # Save the document
        doc.save(output_path)
    
    def analyze(self, resume_text, job_text):
        """Main analysis"""
        match_score, matching_keywords, missing_keywords = self.calculate_match_score(resume_text, job_text)
        
        # Add missing keywords
        optimized_resume = self.add_missing_keywords(resume_text, missing_keywords)
        
        # Save to Word
        filename = self.generate_filename(resume_text, job_text)
        docx_path = os.path.join(app.config['OPTIMIZED_FOLDER'], filename)
        self.create_beautiful_word(optimized_resume, docx_path)
        
        name = self.extract_name_from_resume(resume_text)
        
        return {
            'match_score': round(match_score, 1),
            'matching_keywords': list(matching_keywords)[:20],
            'missing_keywords': list(missing_keywords)[:20],
            'total_matching': len(matching_keywords),
            'total_missing': len(missing_keywords),
            'verdict': 'good' if match_score >= 70 else 'moderate' if match_score >= 50 else 'poor',
            'filename': filename,
            'name': name
        }

matcher = ResumeMatcher()

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resume Optimizer - Beautiful Word Output</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        h1 {
            text-align: center;
            color: white;
            margin-bottom: 10px;
        }
        
        .subtitle {
            text-align: center;
            color: white;
            margin-bottom: 30px;
            opacity: 0.9;
        }
        
        .badge {
            background: #2196f3;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 12px;
            margin-left: 10px;
        }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .card h3 {
            margin-top: 0;
            color: #333;
            margin-bottom: 15px;
        }
        
        textarea {
            width: 100%;
            height: 500px;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            resize: vertical;
        }
        
        textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        
        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
        }
        
        button:hover {
            opacity: 0.9;
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .results {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
            display: none;
        }
        
        .score-card {
            text-align: center;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            color: white;
            margin-bottom: 20px;
        }
        
        .score-number {
            font-size: 48px;
            font-weight: bold;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat {
            background: #f8f9fa;
            padding: 15px;
            text-align: center;
            border-radius: 8px;
        }
        
        .stat-number {
            font-size: 28px;
            font-weight: bold;
            color: #667eea;
        }
        
        .keywords {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }
        
        .tag {
            display: inline-block;
            padding: 5px 12px;
            margin: 5px;
            border-radius: 20px;
            font-size: 12px;
        }
        
        .tag-matching {
            background: #4caf50;
            color: white;
        }
        
        .tag-missing {
            background: #ff9800;
            color: white;
        }
        
        .download-btn {
            background: #4caf50;
            margin-top: 10px;
        }
        
        .good { color: #4caf50; }
        .moderate { color: #ff9800; }
        .poor { color: #ff9800; }
        
        .example {
            font-size: 12px;
            color: rgba(255,255,255,0.8);
            margin-top: 10px;
            text-align: center;
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            .stats {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 Resume Optimizer <span class="badge">Word Format</span></h1>
        <p class="subtitle">Paste your resume and job description - Get a beautifully formatted Word document</p>
        
        <div class="grid">
            <div class="card">
                <h3>📝 Your Resume (Paste here)</h3>
                <textarea id="resumeText" placeholder="Paste your resume here...&#10;&#10;Example:&#10;RISHI KUMAR SONI&#10;rishisoni1945@gmail.com | LinkedIn: linkedin.com/in/rishi-k-soni&#10;&#10;ABOUT ME&#10;DevOps Engineer with 5+ years of experience...&#10;&#10;CORE SKILLS&#10;Python, Java, AWS, Docker, Kubernetes"></textarea>
            </div>
            
            <div class="card">
                <h3>💼 Job Description (Paste here)</h3>
                <textarea id="jobText" placeholder="Paste the job description here..."></textarea>
            </div>
        </div>
        
        <button onclick="analyze()" id="analyzeBtn">🎨 Create Beautiful Word Document</button>
        
        <div class="example">
            ✨ Features: Centered name, professional headings, colored section headers, bullet points, and clean formatting
        </div>
        
        <div class="results" id="results"></div>
    </div>
    
    <script>
        let currentFile = '';
        
        async function analyze() {
            const resumeText = document.getElementById('resumeText').value;
            const jobText = document.getElementById('jobText').value;
            
            if (!resumeText.trim() || !jobText.trim()) {
                alert('Please paste both your resume and the job description');
                return;
            }
            
            const btn = document.getElementById('analyzeBtn');
            btn.disabled = true;
            btn.innerHTML = '⏳ Creating Beautiful Word Document...';
            
            const formData = new FormData();
            formData.append('resume_text', resumeText);
            formData.append('job_text', jobText);
            
            try {
                const response = await fetch('/analyze', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (response.ok) {
                    currentFile = data.filename;
                    displayResults(data);
                    
                    setTimeout(() => {
                        window.location.href = '/download/' + data.filename;
                    }, 500);
                } else {
                    alert(data.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '🎨 Create Beautiful Word Document';
            }
        }
        
        function displayResults(data) {
            const verdictClass = data.verdict;
            const verdictText = data.verdict === 'good' ? '✅ GOOD MATCH!' : 
                               (data.verdict === 'moderate' ? '⚠️ MODERATE MATCH' : '❌ LOW MATCH');
            
            const html = `
                <div class="score-card">
                    <div class="score-number">${data.match_score}%</div>
                    <div class="${verdictClass}" style="font-size: 20px;">${verdictText}</div>
                </div>
                
                <div class="stats">
                    <div class="stat">
                        <div class="stat-number">${data.total_matching}</div>
                        <div>Keywords Found</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">${data.total_missing}</div>
                        <div>Keywords Added</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">${data.name}</div>
                        <div>Candidate</div>
                    </div>
                </div>
                
                <div class="keywords">
                    <strong>✅ Keywords found in your resume (${data.matching_keywords.length}):</strong><br>
                    ${data.matching_keywords.map(k => `<span class="tag tag-matching">${k}</span>`).join('') || 'None'}
                </div>
                
                <div class="keywords">
                    <strong>✨ Missing keywords added to your resume (${data.missing_keywords.length}):</strong><br>
                    ${data.missing_keywords.map(k => `<span class="tag tag-missing">${k}</span>`).join('') || 'None'}
                </div>
                
                <div style="text-align: center;">
                    <p>✅ <strong>Beautiful Word document saved as:</strong> ${data.filename}</p>
                    <button class="download-btn" onclick="window.location.href='/download/${data.filename}'">
                        📥 Download Word Document
                    </button>
                </div>
            `;
            
            document.getElementById('results').style.display = 'block';
            document.getElementById('results').innerHTML = html;
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        resume_text = request.form.get('resume_text')
        job_text = request.form.get('job_text')
        
        if not resume_text or not job_text:
            return jsonify({'error': 'Please provide both resume and job description text'}), 400
        
        results = matcher.analyze(resume_text, job_text)
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['OPTIMIZED_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_file(
            file_path, 
            as_attachment=True, 
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 RESUME OPTIMIZER - BEAUTIFUL WORD OUTPUT")
    print("="*70)
    print("\n✅ Server started at: http://localhost:5000")
    print("📝 PASTE your resume text")
    print("📝 PASTE job description")
    print("🎨 Creates BEAUTIFULLY formatted Word document with:")
    print("   • Centered name at the top")
    print("   • Professional colored headings (blue with underline)")
    print("   • Clean bullet points")
    print("   • Bold company names")
    print("   • Proper spacing and margins")
    print("📥 Downloads as Word document")
    print("\n⚠️  Press CTRL+C to stop\n")
    app.run(debug=True, host='127.0.0.1', port=5000)