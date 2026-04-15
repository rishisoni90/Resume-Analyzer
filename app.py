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
        
        # Quantified impact patterns to detect
        self.impact_patterns = [
            r'\b\d+%?\b',  # Numbers with optional %
            r'\b\d+(?:\.\d+)?\s*(?:x|times)\b',  # 2x, 3 times
            r'\$\d+(?:,\d+)?(?:\s*(?:million|billion|k|M|B))?',  # $ amounts
            r'\b(?:increased|decreased|reduced|improved|boosted|saved|generated|delivered)\s+\w+\s+\d+%?',  # Action + metric
            r'\b(?:from\s+\d+\s+to\s+\d+)\b',  # Range improvements
            r'\b\d+\s*(?:years?|months?|weeks?|days?)',  # Time periods
            r'\b(?:over\s+\d+%?)\b',  # Over X%
            r'\b(?:reduced by|increased by|improved by)\s+\d+%?\b'  # Percentage changes
        ]
        
        # Common action verbs for impact statements
        self.impact_verbs = ['increased', 'decreased', 'reduced', 'improved', 'boosted', 
                            'saved', 'generated', 'delivered', 'achieved', 'accelerated',
                            'optimized', 'enhanced', 'streamlined', 'cut', 'lowered',
                            'grew', 'expanded', 'maximized', 'minimized']
        
        # Industry-standard metrics
        self.metric_suggestions = {
            'software': ['response time', 'deployment frequency', 'bug rate', 'code coverage', 'load time'],
            'sales': ['revenue', 'conversion rate', 'customer acquisition', 'retention rate', 'deal size'],
            'marketing': ['engagement rate', 'click-through rate', 'ROI', 'traffic', 'lead generation'],
            'operations': ['efficiency', 'turnaround time', 'cost reduction', 'productivity', 'throughput'],
            'management': ['team productivity', 'project completion', 'budget management', 'resource utilization']
        }

    def preprocess_text(self, text):
        """Clean and preprocess text for keyword matching"""
        text = text.lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        words = word_tokenize(text)
        words = [self.lemmatizer.lemmatize(word) for word in words 
                if word not in self.stop_words and len(word) > 2]
        return words
    
    def extract_quantified_impacts(self, text):
        """Extract all quantified achievements from text"""
        impacts = []
        
        for pattern in self.impact_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            impacts.extend(matches)
        
        # Extract full impact sentences
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            if any(verb in sentence.lower() for verb in self.impact_verbs):
                if re.search(r'\d+', sentence):
                    impacts.append(sentence.strip())
        
        return list(set(impacts))  # Remove duplicates
    
    def analyze_impact_quality(self, resume_text):
        """Analyze the quality and quantity of quantified impacts"""
        impacts = self.extract_quantified_impacts(resume_text)
        
        # Count metrics by category
        metrics_count = {
            'percentages': len(re.findall(r'\d+%', resume_text)),
            'currency': len(re.findall(r'\$\d+', resume_text)),
            'numbers': len(re.findall(r'\b\d+\b', resume_text)),
            'time_based': len(re.findall(r'\d+\s*(?:years?|months?|weeks?|days?)', resume_text, re.IGNORECASE)),
            'action_verbs': len([v for v in self.impact_verbs if v in resume_text.lower()])
        }
        
        impact_score = min(100, (len(impacts) * 10) + (metrics_count['percentages'] * 5) + (metrics_count['currency'] * 3))
        
        return {
            'total_impacts': len(impacts),
            'impacts_list': impacts[:15],  # Show top 15
            'metrics_count': metrics_count,
            'impact_score': impact_score,
            'needs_improvement': impact_score < 60,
            'suggestions': self.generate_impact_suggestions(metrics_count, resume_text)
        }
    
    def generate_impact_suggestions(self, metrics_count, resume_text):
        """Generate specific suggestions for adding quantified impacts"""
        suggestions = []
        
        if metrics_count['percentages'] < 2:
            suggestions.append("📊 Add percentage improvements (e.g., 'increased efficiency by 25%')")
        
        if metrics_count['currency'] == 0:
            suggestions.append("💰 Include financial impact (e.g., 'saved $50,000', 'generated $1M revenue')")
        
        if metrics_count['time_based'] < 2:
            suggestions.append("⏱️ Add time-based metrics (e.g., 'reduced delivery time by 3 days', 'completed in 2 weeks')")
        
        if metrics_count['action_verbs'] < 5:
            suggestions.append("⚡ Use strong action verbs with numbers (e.g., 'improved', 'accelerated', 'optimized')")
        
        # Check for common missing metrics based on resume content
        for category, metrics in self.metric_suggestions.items():
            if any(keyword in resume_text.lower() for keyword in [category, 'software', 'tech', 'developer']):
                suggestions.append(f"💡 For {category} role, consider adding: {', '.join(metrics[:3])}")
                break
        
        if not suggestions:
            suggestions.append("✅ Great job including quantified impacts! Consider adding more specific metrics where possible.")
        
        return suggestions
    
    def add_quantified_impacts(self, resume_text, impact_analysis):
        """Add quantified impact suggestions to the resume"""
        if not impact_analysis['needs_improvement']:
            return resume_text
        
        # Create impact improvement section
        impact_section = "\n\nKEY ACHIEVEMENTS & IMPACT METRICS\n"
        
        # Add specific suggestions as bullet points
        for suggestion in impact_analysis['suggestions'][:4]:  # Add top 4 suggestions
            if suggestion.startswith("💡") or suggestion.startswith("📊") or suggestion.startswith("💰"):
                # Convert suggestion to actionable bullet point
                action = suggestion.split(" ", 1)[1] if " " in suggestion else suggestion
                impact_section += f"  • {action}\n"
        
        # Add example impact statements
        impact_section += "\n  Example impact statements to consider:\n"
        examples = [
            "  • Increased team productivity by 35% through process optimization",
            "  • Reduced operational costs by $100,000 annually",
            "  • Delivered project 2 weeks ahead of schedule, saving 200+ hours",
            "  • Improved customer satisfaction score from 85% to 94%"
        ]
        
        for example in examples[:3]:
            impact_section += f"    {example}\n"
        
        # Insert impact section before skills or at the end
        lines = resume_text.split('\n')
        new_lines = []
        added = False
        
        for i, line in enumerate(lines):
            new_lines.append(line)
            if not added and ('SKILLS' in line.upper() or 'CORE SKILLS' in line.upper()):
                new_lines.append(impact_section)
                added = True
        
        if not added:
            new_lines.append(impact_section)
        
        return '\n'.join(new_lines)
    
    def calculate_match_score(self, resume_text, job_text):
        """Calculate match percentage"""
        resume_keywords = set(self.preprocess_text(resume_text))
        job_keywords = set(self.preprocess_text(job_text))
        
        if not job_keywords:
            return 0, set(), set(), {}
        
        matches = resume_keywords.intersection(job_keywords)
        match_percentage = (len(matches) / len(job_keywords)) * 100
        
        # Add impact quality score to overall match
        impact_analysis = self.analyze_impact_quality(resume_text)
        impact_bonus = impact_analysis['impact_score'] * 0.1  # Up to 10% bonus for good impacts
        final_score = min(100, match_percentage + impact_bonus)
        
        return final_score, matches, job_keywords - resume_keywords, impact_analysis
    
    def extract_name_from_resume(self, text):
        """Extract name from first line"""
        lines = text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 50 and not any(x in line.lower() for x in ['@', 'linkedin', 'github']):
                name = re.sub(r'[^\w\s]', '', line)
                name = re.sub(r'\s+', '_', name.strip())
                return name
        return "Resume"
    
    def extract_contact_info(self, text):
        """Extract contact info lines"""
        lines = text.strip().split('\n')
        for line in lines:
            if '@' in line or 'linkedin' in line.lower() or 'github' in line.lower():
                return line.strip()
        return ""
    
    def extract_job_role(self, job_text):
        """Extract job role from job description"""
        lines = job_text.split('\n')[:30]
        job_roles = [
            'Software Engineer', 'DevOps Engineer', 'Data Scientist', 'Product Manager',
            'Project Manager', 'Frontend Developer', 'Backend Developer', 'Full Stack',
            'Machine Learning', 'AI Engineer', 'Cloud Engineer', 'Security Engineer',
            'QA Engineer', 'DevOps', 'SRE', 'System Administrator', 'Network Engineer',
            'Database Administrator', 'Business Analyst', 'Data Analyst', 'UX Designer',
            'UI Designer', 'Technical Lead', 'Architect', 'Scrum Master', 'Agile Coach'
        ]
        
        for line in lines:
            for role in job_roles:
                if role.lower() in line.lower():
                    clean_role = re.sub(r'[^\w\s]', '', role)
                    clean_role = re.sub(r'\s+', '_', clean_role.strip())
                    return clean_role
        
        title_patterns = [
            r'(?:Job Title|Position|Role)[:\s]+([A-Za-z\s]+)',
            r'([A-Za-z\s]+(?:Engineer|Developer|Manager|Analyst|Specialist|Consultant))'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, job_text, re.IGNORECASE)
            if match:
                role = match.group(1).strip()
                clean_role = re.sub(r'[^\w\s]', '', role)
                clean_role = re.sub(r'\s+', '_', clean_role.strip())
                return clean_role
        
        return "Position"
    
    def generate_filename(self, resume_text, job_text):
        """Generate filename: FirstName_LastName_JobRole_Date.docx"""
        full_name = self.extract_name_from_resume(resume_text)
        name_parts = full_name.split('_')
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = name_parts[1]
            formatted_name = f"{first_name}_{last_name}"
        else:
            formatted_name = full_name
        
        job_role = self.extract_job_role(job_text)
        date = datetime.now().strftime("%Y%m%d")
        filename = f"{formatted_name}_{job_role}_{date}.docx"
        filename = re.sub(r'_+', '_', filename)
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        
        return filename
    
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
            if not added and ('CORE SKILLS' in line or 'SKILLS' in line or 'TECHNICAL SKILLS' in line):
                new_lines.append(f"  {keywords_to_add}")
                added = True
        
        if not added:
            new_lines.insert(3, f"\nSKILLS\n{keywords_to_add}\n")
        
        return '\n'.join(new_lines)
    
    def create_beautiful_word(self, text, output_path, impact_analysis=None):
        """Create beautifully formatted Word document with impact metrics"""
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
            
            # Check if this is the name line
            if not name_added and len(line) < 50 and not any(x in line.lower() for x in ['@', 'linkedin', 'github', '|']):
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
            
            # Check if it's a section header
            if line.isupper() and len(line) < 50:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(6)
                run = p.add_run(line)
                run.font.name = 'Calibri'
                run.font.size = Pt(16)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0, 51, 102)
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
                
                # Highlight quantified impacts in green
                impact_matches = re.findall(r'\b\d+%?\b|\$\d+(?:,\d+)?', bullet_text)
                if impact_matches:
                    run.font.color.rgb = RGBColor(0, 128, 0)  # Green for metrics
                continue
            
            # Check if it's a skill category
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
        
        # Add impact analysis summary page if improvements were suggested
        if impact_analysis and impact_analysis.get('needs_improvement'):
            doc.add_page_break()
            
            # Impact Analysis Header
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run("IMPACT METRICS ANALYSIS")
            run.font.name = 'Calibri'
            run.font.size = Pt(18)
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 0, 0)
            
            # Score card
            p = doc.add_paragraph()
            run = p.add_run(f"Impact Score: {impact_analysis['impact_score']}/100")
            run.font.name = 'Calibri'
            run.font.size = Pt(14)
            run.font.bold = True
            
            # Suggestions
            p = doc.add_paragraph()
            run = p.add_run("Suggestions for Improvement:")
            run.font.name = 'Calibri'
            run.font.size = Pt(12)
            run.font.bold = True
            
            for suggestion in impact_analysis['suggestions']:
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.25)
                run = p.add_run(f"• {suggestion}")
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
        
        doc.save(output_path)
    
    def analyze(self, resume_text, job_text):
        """Main analysis with quantified impact"""
        match_score, matching_keywords, missing_keywords, impact_analysis = self.calculate_match_score(resume_text, job_text)
        
        # Add missing keywords
        optimized_resume = self.add_missing_keywords(resume_text, missing_keywords)
        
        # Add quantified impact suggestions if needed
        if impact_analysis['needs_improvement']:
            optimized_resume = self.add_quantified_impacts(optimized_resume, impact_analysis)
        
        # Save to Word
        filename = self.generate_filename(resume_text, job_text)
        docx_path = os.path.join(app.config['OPTIMIZED_FOLDER'], filename)
        self.create_beautiful_word(optimized_resume, docx_path, impact_analysis)
        
        name = self.extract_name_from_resume(resume_text).replace('_', ' ')
        
        return {
            'match_score': round(match_score, 1),
            'impact_score': impact_analysis['impact_score'],
            'matching_keywords': list(matching_keywords)[:20],
            'missing_keywords': list(missing_keywords)[:20],
            'total_matching': len(matching_keywords),
            'total_missing': len(missing_keywords),
            'total_impacts': impact_analysis['total_impacts'],
            'impact_suggestions': impact_analysis['suggestions'][:5],
            'verdict': 'excellent' if match_score >= 80 else 'good' if match_score >= 65 else 'moderate' if match_score >= 50 else 'poor',
            'filename': filename,
            'name': name
        }

matcher = ResumeMatcher()

# HTML Template (updated to show impact metrics)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resume Optimizer - Quantified Impact Edition</title>
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
            background: #ff9800;
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
            grid-template-columns: repeat(4, 1fr);
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
        
        .excellent { color: #4caf50; }
        .good { color: #8bc34a; }
        .moderate { color: #ff9800; }
        .poor { color: #f44336; }
        
        .example {
            font-size: 12px;
            color: rgba(255,255,255,0.8);
            margin-top: 10px;
            text-align: center;
        }
        
        .impact-suggestion {
            background: #e3f2fd;
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            font-size: 13px;
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
        <h1>📊 Resume Optimizer <span class="badge">Quantified Impact Edition</span></h1>
        <p class="subtitle">Add numbers, metrics, and measurable achievements to your resume</p>
        
        <div class="grid">
            <div class="card">
                <h3>📝 Your Resume (Paste here)</h3>
                <textarea id="resumeText" placeholder="Paste your resume here...&#10;&#10;💡 TIP: Include numbers and metrics for better results!&#10;&#10;Example:&#10;Rishi Soni&#10;rishisoni1945@gmail.com&#10;&#10;DevOps Engineer with 5+ years experience&#10;• Increased deployment frequency by 300%&#10;• Reduced costs by $100,000 annually&#10;• Improved system uptime from 99.5% to 99.9%"></textarea>
            </div>
            
            <div class="card">
                <h3>💼 Job Description (Paste here)</h3>
                <textarea id="jobText" placeholder="Paste the job description here...&#10;&#10;Example:&#10;Job Title: DevOps Engineer&#10;Looking for engineer with experience in AWS, Docker, Kubernetes..."></textarea>
            </div>
        </div>
        
        <button onclick="analyze()" id="analyzeBtn">🎯 Optimize with Quantified Impact</button>
        
        <div class="example">
            ✨ NEW: Detects and suggests quantified achievements (%, $, time savings, performance metrics)
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
            btn.innerHTML = '⏳ Analyzing and Adding Quantified Impact...';
            
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
                        window.location.href = '/download/' + encodeURIComponent(data.filename);
                    }, 500);
                } else {
                    alert(data.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '🎯 Optimize with Quantified Impact';
            }
        }
        
        function displayResults(data) {
            const verdictClass = data.verdict;
            const verdictText = {
                'excellent': '🏆 EXCELLENT MATCH!',
                'good': '✅ GOOD MATCH',
                'moderate': '⚠️ MODERATE MATCH',
                'poor': '❌ NEEDS IMPROVEMENT'
            }[data.verdict];
            
            let impactHtml = '';
            if (data.impact_suggestions && data.impact_suggestions.length > 0) {
                impactHtml = '<div class="keywords"><strong>📊 Impact Improvement Suggestions:</strong><br>';
                data.impact_suggestions.forEach(suggestion => {
                    impactHtml += `<div class="impact-suggestion">${suggestion}</div>`;
                });
                impactHtml += '</div>';
            }
            
            const html = `
                <div class="score-card">
                    <div class="score-number">${data.match_score}%</div>
                    <div class="${verdictClass}" style="font-size: 20px;">${verdictText}</div>
                    <div style="font-size: 14px; margin-top: 10px;">Impact Score: ${data.impact_score || 0}/100</div>
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
                        <div class="stat-number">${data.total_impacts || 0}</div>
                        <div>Quantified Impacts</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">${data.name}</div>
                        <div>Candidate</div>
                    </div>
                </div>
                
                <div class="keywords">
                    <strong>✅ Keywords found (${data.matching_keywords.length}):</strong><br>
                    ${data.matching_keywords.map(k => `<span class="tag tag-matching">${k}</span>`).join('') || 'None'}
                </div>
                
                <div class="keywords">
                    <strong>✨ Keywords added (${data.missing_keywords.length}):</strong><br>
                    ${data.missing_keywords.map(k => `<span class="tag tag-missing">${k}</span>`).join('') || 'None'}
                </div>
                
                ${impactHtml}
                
                <div style="text-align: center;">
                    <p>✅ <strong>Optimized resume saved as:</strong> ${data.filename}</p>
                    <button class="download-btn" onclick="window.location.href='/download/' + encodeURIComponent('${data.filename}')">
                        📥 Download Optimized Resume (Word)
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

@app.route('/download/<path:filename>')
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
    print("📊 RESUME OPTIMIZER - QUANTIFIED IMPACT EDITION")
    print("="*70)
    print("\n✅ Server started at: http://localhost:5000")
    print("\n🎯 NEW FEATURES ADDED:")
    print("   • Detects quantified achievements (%, $, time metrics)")
    print("   • Calculates Impact Score (0-100)")
    print("   • Suggests specific metrics to add")
    print("   • Highlights numbers in green in Word output")
    print("   • Adds impact analysis section for weak resumes")
    print("   • Provides industry-specific metric suggestions")
    print("\n📝 ENHANCED MATCHING:")
    print("   • Keyword matching + Impact Quality bonus")
    print("   • Up to 10% bonus for strong quantified impacts")
    print("\n📁 Output includes impact suggestions in Word document")
    print("\n⚠️  Press CTRL+C to stop\n")
    app.run(debug=True, host='127.0.0.1', port=5000)