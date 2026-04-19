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
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)

app = Flask(__name__)
app.config['OPTIMIZED_FOLDER'] = 'optimized_resumes'
os.makedirs(app.config['OPTIMIZED_FOLDER'], exist_ok=True)

SKILL_SYNONYMS = {
    'javascript': ['js', 'ecmascript', 'nodejs', 'node.js', 'react', 'vue', 'angular'],
    'python': ['py', 'django', 'flask', 'fastapi', 'pandas', 'numpy', 'scikit'],
    'java': ['spring', 'springboot', 'spring boot', 'j2ee', 'hibernate'],
    'aws': ['amazon web services', 'ec2', 's3', 'lambda', 'cloudformation', 'dynamodb'],
    'docker': ['containers', 'containerization', 'dockerfile', 'docker-compose'],
    'kubernetes': ['k8s', 'helm', 'kustomize', 'openshift'],
    'sql': ['database', 'mysql', 'postgresql', 'postgres', 'mongodb', 'nosql', 'db'],
    'git': ['version control', 'github', 'gitlab', 'bitbucket', 'vcs'],
    'ci/cd': ['continuous integration', 'continuous deployment', 'jenkins', 'github actions', 'circleci'],
    'agile': ['scrum', 'kanban', 'sprint', 'jira', 'confluence'],
    'leadership': ['leading', 'managed', 'mentored', 'team lead', 'supervised'],
    'communication': ['presentation', 'documentation', 'stakeholder', 'collaboration'],
    'machine learning': ['ml', 'ai', 'deep learning', 'neural networks', 'tensorflow', 'pytorch'],
    'cloud': ['azure', 'gcp', 'google cloud', 'serverless', 'cloud computing'],
    'devops': ['sre', 'site reliability', 'infrastructure', 'automation', 'terraform'],
    'testing': ['qa', 'quality assurance', 'unit testing', 'integration testing', 'selenium'],
}

HIGH_WEIGHT_KEYWORDS = [
    'architecture', 'design', 'lead', 'senior', 'principal', 'staff',
    'scalability', 'performance', 'optimization', 'security', 'production',
    'system', 'distributed', 'microservices', 'api', 'cloud', 'aws', 'azure', 'gcp'
]

MEDIUM_WEIGHT_KEYWORDS = [
    'experience', 'development', 'implementation', 'deployment', 'testing',
    'collaboration', 'team', 'agile', 'scrum', 'ci/cd', 'docker', 'kubernetes'
]


class ResumeMatcher:
    def __init__(self):
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
        self.impact_verbs = ['increased', 'decreased', 'reduced', 'improved', 'boosted',
                             'saved', 'generated', 'delivered', 'achieved', 'accelerated',
                             'optimized', 'enhanced', 'streamlined', 'cut', 'lowered',
                             'grew', 'expanded', 'maximized', 'minimized', 'led', 'built',
                             'launched', 'deployed', 'automated', 'engineered', 'designed']

    def preprocess_text(self, text):
        text = text.lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        words = word_tokenize(text)
        words = [self.lemmatizer.lemmatize(w) for w in words
                 if w not in self.stop_words and len(w) > 2]
        return words

    def extract_skills_with_synonyms(self, text):
        text_lower = text.lower()
        skills = set(self.preprocess_text(text))
        for skill, synonyms in SKILL_SYNONYMS.items():
            if skill in text_lower or any(s in text_lower for s in synonyms):
                skills.add(skill)
                skills.update(synonyms)
        return skills

    def analyze_impact_quality(self, resume_text):
        impact_patterns = [
            r'\b\d+%?\b', r'\$\d+(?:,\d+)?(?:\s*(?:million|billion|k|M|B))?',
            r'\b\d+\s*(?:years?|months?|weeks?|days?)',
        ]
        impacts = []
        for pat in impact_patterns:
            impacts.extend(re.findall(pat, resume_text))
        sentences = re.split(r'[.!?\n]+', resume_text)
        for s in sentences:
            if any(v in s.lower() for v in self.impact_verbs) and re.search(r'\d+', s):
                impacts.append(s.strip())
        metrics = {
            'percentages': len(re.findall(r'\d+%', resume_text)),
            'currency': len(re.findall(r'\$\d+', resume_text)),
            'numbers': len(re.findall(r'\b\d+\b', resume_text)),
            'action_verbs': len([v for v in self.impact_verbs if v in resume_text.lower()])
        }
        score = min(100, (len(set(impacts)) * 8) + (metrics['percentages'] * 6) + (metrics['currency'] * 4) + (metrics['action_verbs'] * 2))
        suggestions = []
        if metrics['percentages'] < 2:
            suggestions.append("Add percentage improvements (e.g., 'Increased efficiency by 35%', 'Reduced error rate by 60%')")
        if metrics['currency'] == 0:
            suggestions.append("Include dollar amounts (e.g., 'Saved $50,000 annually', 'Managed $500K budget')")
        if metrics['action_verbs'] < 5:
            suggestions.append("Start bullets with strong action verbs: 'Led', 'Architected', 'Optimized', 'Delivered', 'Automated'")
        if len(set(impacts)) < 3:
            suggestions.append("Add time-based achievements (e.g., 'Reduced processing time from 4 hours to 30 minutes')")
        if not suggestions:
            suggestions.append("Great job! Your resume has strong quantified impacts.")
        return {
            'total_impacts': len(set(impacts)),
            'metrics_count': metrics,
            'impact_score': score,
            'needs_improvement': score < 60,
            'suggestions': suggestions
        }

    def calculate_match_score(self, resume_text, job_text):
        resume_skills = self.extract_skills_with_synonyms(resume_text)
        job_skills = self.extract_skills_with_synonyms(job_text)
        if not job_skills:
            return 0, set(), set(), {}
        matches = resume_skills.intersection(job_skills)
        weighted_match = 0
        weighted_total = 0
        for kw in job_skills:
            w = 1.5 if kw in HIGH_WEIGHT_KEYWORDS else (1.2 if kw in MEDIUM_WEIGHT_KEYWORDS else 1.0)
            weighted_total += w
            if kw in matches:
                weighted_match += w
        pct = (weighted_match / weighted_total * 100) if weighted_total > 0 else 0
        impact = self.analyze_impact_quality(resume_text)
        bonus = impact['impact_score'] * 0.1
        exp_bonus = self._exp_bonus(resume_text, job_text)
        final = min(100, pct + bonus + exp_bonus)
        return final, matches, job_skills - resume_skills, impact

    def _exp_bonus(self, resume_text, job_text):
        r = re.findall(r'(\d+)\s*(?:years?|yrs?)', resume_text, re.IGNORECASE)
        j = re.findall(r'(\d+)\s*(?:years?|yrs?)', job_text, re.IGNORECASE)
        if r and j and int(max(r)) >= int(min(j)):
            return 5
        return 0

    def extract_name(self, text, for_display=True):
        lines = text.strip().split('\n')
        for line in lines[:5]:
            line = line.strip()
            if not line:
                continue
            if any(x in line.lower() for x in ['@', 'linkedin', 'github', 'http', 'www.', 'phone', '+', '|']):
                continue
            if any(x in line.lower() for x in ['experience', 'education', 'skills', 'summary']):
                continue
            if 2 < len(line) < 50 and re.match(r'^[A-Za-z\s\.]+$', line):
                name = re.sub(r'\s+', ' ', line.strip())
                if for_display:
                    return name
                return re.sub(r'\s+', '_', name)
        return "Candidate"

    def extract_contact(self, text):
        for line in text.split('\n'):
            if any(x in line.lower() for x in ['@', 'linkedin', 'github', '+', 'phone']):
                return line.strip()
        return ""

    def extract_job_role(self, job_text):
        roles = ['Software Engineer', 'Senior Software Engineer', 'DevOps Engineer',
                 'Site Reliability Engineer', 'Data Scientist', 'Product Manager',
                 'Frontend Developer', 'Backend Developer', 'Full Stack Developer',
                 'Machine Learning Engineer', 'Cloud Engineer', 'Security Engineer',
                 'QA Engineer', 'Technical Lead', 'Engineering Manager', 'Architect']
        for line in job_text.split('\n')[:10]:
            for role in roles:
                if role.lower() in line.lower():
                    return re.sub(r'\s+', '_', role)
        return 'Position'

    def generate_filename(self, resume_text, job_text):
        name = self.extract_name(resume_text, for_display=False)
        role = self.extract_job_role(job_text)
        date = datetime.now().strftime("%Y%m%d")
        fname = f"{name}_{role}_{date}"
        fname = re.sub(r'_+', '_', fname)
        fname = re.sub(r'[<>:"/\\|?*]', '', fname)
        return fname

    def add_missing_keywords(self, resume_text, missing_keywords):
        if not missing_keywords:
            return resume_text
        kws = ', '.join([k.title() for k in list(missing_keywords)[:10]])
        lines = resume_text.split('\n')
        new_lines = []
        added = False
        for line in lines:
            new_lines.append(line)
            if not added and re.search(r'SKILLS|TECHNICAL', line.upper()):
                new_lines.append(f"  {kws}")
                added = True
        if not added:
            new_lines.insert(3, f"\nSKILLS\n{kws}\n")
        return '\n'.join(new_lines)

    # ─────────────────────────────────────────────────────────────
    # BEAUTIFUL PDF — clean, ATS-friendly, professional resume look
    # ─────────────────────────────────────────────────────────────
    def create_beautiful_pdf(self, resume_text, output_path):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.65 * inch,
            leftMargin=0.65 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
        )

        DARK   = colors.HexColor('#1a1a2e')
        BLUE   = colors.HexColor('#0066cc')
        GRAY   = colors.HexColor('#555555')
        LGRAY  = colors.HexColor('#888888')
        GREEN  = colors.HexColor('#1a7a1a')
        WHITE  = colors.white
        LBLUE  = colors.HexColor('#e8f0fe')

        styles = getSampleStyleSheet()

        name_style = ParagraphStyle('Name', fontSize=26, fontName='Helvetica-Bold',
            textColor=DARK, alignment=TA_CENTER, spaceAfter=4)

        contact_style = ParagraphStyle('Contact', fontSize=9.5, fontName='Helvetica',
            textColor=LGRAY, alignment=TA_CENTER, spaceAfter=14)

        section_style = ParagraphStyle('Section', fontSize=11, fontName='Helvetica-Bold',
            textColor=WHITE, spaceBefore=14, spaceAfter=6,
            leftIndent=6, rightIndent=6)

        job_title_style = ParagraphStyle('JobTitle', fontSize=11, fontName='Helvetica-Bold',
            textColor=DARK, spaceBefore=8, spaceAfter=1)

        job_meta_style = ParagraphStyle('JobMeta', fontSize=9.5, fontName='Helvetica',
            textColor=LGRAY, spaceAfter=4)

        bullet_style = ParagraphStyle('Bullet', fontSize=10, fontName='Helvetica',
            textColor=GRAY, spaceBefore=2, spaceAfter=2,
            leftIndent=14, firstLineIndent=-10, leading=14)

        bullet_metric_style = ParagraphStyle('BulletMetric', fontSize=10, fontName='Helvetica-Bold',
            textColor=GREEN, spaceBefore=2, spaceAfter=2,
            leftIndent=14, firstLineIndent=-10, leading=14)

        skill_key_style = ParagraphStyle('SkillKey', fontSize=10, fontName='Helvetica-Bold',
            textColor=DARK, spaceBefore=3, spaceAfter=1)

        skill_val_style = ParagraphStyle('SkillVal', fontSize=10, fontName='Helvetica',
            textColor=GRAY, spaceBefore=0, spaceAfter=3)

        body_style = ParagraphStyle('Body', fontSize=10, fontName='Helvetica',
            textColor=GRAY, spaceBefore=2, spaceAfter=2, leading=14)

        story = []
        name_added = False
        contact_added = False

        lines = resume_text.split('\n')

        for line in lines:
            ls = line.strip()
            if not ls:
                story.append(Spacer(1, 0.06 * inch))
                continue

            # Name
            if not name_added and len(ls) < 60 and \
                not any(x in ls.lower() for x in ['@', 'linkedin', 'github', 'http', '+', '|']):
                story.append(Paragraph(ls, name_style))
                # Thin divider under name
                story.append(HRFlowable(width="100%", thickness=1.5,
                    color=BLUE, spaceAfter=4, spaceBefore=2))
                name_added = True
                continue

            # Contact line
            if not contact_added and any(x in ls.lower() for x in ['@', 'linkedin', 'github', '+', 'http']):
                story.append(Paragraph(ls, contact_style))
                contact_added = True
                continue

            # SECTION HEADERS — coloured background bar
            if ls.isupper() and 3 < len(ls) < 55:
                story.append(Spacer(1, 0.05 * inch))
                # Draw coloured background using a 1-row Table
                tbl = Table([[Paragraph(ls, section_style)]], colWidths=[7.2 * inch])
                tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), BLUE),
                    ('ROUNDEDCORNERS', [4]),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 0.04 * inch))
                continue

            # Job title / subheader (contains | or " at ")
            if '|' in ls and len(ls) < 120:
                parts = ls.split('|')
                story.append(Paragraph(parts[0].strip(), job_title_style))
                if len(parts) > 1:
                    story.append(Paragraph(' | '.join(p.strip() for p in parts[1:]), job_meta_style))
                continue

            # Skill lines "Category: values"
            if ':' in ls and len(ls.split(':')) == 2 and len(ls) < 120:
                key, val = ls.split(':', 1)
                story.append(Paragraph(f"<b>{key.strip()}:</b>", skill_key_style))
                story.append(Paragraph(val.strip(), skill_val_style))
                continue

            # Bullet points
            if ls.startswith(('•', '-', '*', '●')):
                text = ls[1:].strip()
                has_metric = bool(re.search(
                    r'\d+%|\$\d+|\d+\s*(years?|months?|hours?|weeks?|x\b|times?)',
                    text, re.IGNORECASE))
                style = bullet_metric_style if has_metric else bullet_style
                story.append(Paragraph(f"• {text}", style))
                continue

            # Regular paragraph
            story.append(Paragraph(ls, body_style))

        doc.build(story)
        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())

    # ─────────────────────────────────────────────────────────────
    # BEAUTIFUL WORD DOC
    # ─────────────────────────────────────────────────────────────
    def create_beautiful_word(self, resume_text, output_path):
        doc = Document()
        for section in doc.sections:
            section.top_margin    = Inches(0.7)
            section.bottom_margin = Inches(0.7)
            section.left_margin   = Inches(0.75)
            section.right_margin  = Inches(0.75)

        lines = resume_text.split('\n')
        name_added = False
        contact_added = False

        for line in lines:
            ls = line.strip()

            if not ls:
                doc.add_paragraph()
                continue

            # Name
            if not name_added and len(ls) < 60 and \
                not any(x in ls.lower() for x in ['@', 'linkedin', 'github', 'http', '+', '|']):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(ls)
                r.font.name = 'Calibri Light'
                r.font.size = Pt(28)
                r.font.bold = True
                r.font.color.rgb = RGBColor(26, 26, 46)
                p.paragraph_format.space_after = Pt(4)
                # Thin blue line
                lp = doc.add_paragraph()
                lp_r = lp.add_run('─' * 80)
                lp_r.font.size = Pt(6)
                lp_r.font.color.rgb = RGBColor(0, 102, 204)
                lp.paragraph_format.space_after = Pt(4)
                name_added = True
                continue

            # Contact
            if not contact_added and any(x in ls.lower() for x in ['@', 'linkedin', 'github', '+', 'http']):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(ls)
                r.font.name = 'Calibri'
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(136, 136, 136)
                p.paragraph_format.space_after = Pt(10)
                contact_added = True
                continue

            # SECTION HEADERS
            if ls.isupper() and 3 < len(ls) < 55:
                p = doc.add_paragraph()
                r = p.add_run(f'  {ls}  ')
                r.font.name = 'Calibri'
                r.font.size = Pt(11)
                r.font.bold = True
                r.font.color.rgb = RGBColor(255, 255, 255)
                p.paragraph_format.space_before = Pt(14)
                p.paragraph_format.space_after = Pt(6)
                from docx.oxml.ns import qn
                from docx.oxml import OxmlElement
                pPr = p._p.get_or_add_pPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), '0066CC')
                pPr.append(shd)
                continue

            # Job title with |
            if '|' in ls and len(ls) < 120:
                parts = ls.split('|')
                p = doc.add_paragraph()
                r = p.add_run(parts[0].strip())
                r.font.name = 'Calibri'
                r.font.size = Pt(11)
                r.font.bold = True
                r.font.color.rgb = RGBColor(26, 26, 46)
                p.paragraph_format.space_before = Pt(8)
                p.paragraph_format.space_after = Pt(2)
                if len(parts) > 1:
                    mp = doc.add_paragraph()
                    mr = mp.add_run(' | '.join(p2.strip() for p2 in parts[1:]))
                    mr.font.name = 'Calibri'
                    mr.font.size = Pt(9.5)
                    mr.font.color.rgb = RGBColor(136, 136, 136)
                    mp.paragraph_format.space_after = Pt(4)
                continue

            # Skill key: value
            if ':' in ls and len(ls.split(':')) == 2 and len(ls) < 120:
                key, val = ls.split(':', 1)
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(2)
                r1 = p.add_run(key.strip() + ': ')
                r1.font.name = 'Calibri'
                r1.font.size = Pt(10)
                r1.font.bold = True
                r1.font.color.rgb = RGBColor(26, 26, 46)
                r2 = p.add_run(val.strip())
                r2.font.name = 'Calibri'
                r2.font.size = Pt(10)
                r2.font.color.rgb = RGBColor(80, 80, 80)
                continue

            # Bullets
            if ls.startswith(('•', '-', '*', '●')):
                text = ls[1:].strip()
                has_metric = bool(re.search(
                    r'\d+%|\$\d+|\d+\s*(years?|months?|hours?|weeks?|x\b)',
                    text, re.IGNORECASE))
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.25)
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.25
                r = p.add_run(f'•  {text}')
                r.font.name = 'Calibri'
                r.font.size = Pt(10.5)
                if has_metric:
                    r.font.color.rgb = RGBColor(26, 122, 26)
                    r.font.bold = True
                else:
                    r.font.color.rgb = RGBColor(60, 60, 60)
                continue

            # Normal
            p = doc.add_paragraph()
            r = p.add_run(ls)
            r.font.name = 'Calibri'
            r.font.size = Pt(10.5)
            r.font.color.rgb = RGBColor(60, 60, 60)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)

        doc.save(output_path)

    def analyze(self, resume_text, job_text):
        score, matches, missing, impact = self.calculate_match_score(resume_text, job_text)
        optimized = self.add_missing_keywords(resume_text, missing)
        base = self.generate_filename(resume_text, job_text)
        docx_path = os.path.join(app.config['OPTIMIZED_FOLDER'], base + '.docx')
        pdf_path  = os.path.join(app.config['OPTIMIZED_FOLDER'], base + '.pdf')
        self.create_beautiful_word(optimized, docx_path)
        self.create_beautiful_pdf(optimized, pdf_path)
        score_r = round(score, 1)
        if score_r >= 85:   verdict, msg = 'excellent', 'Excellent match! Your resume is strongly aligned.'
        elif score_r >= 70: verdict, msg = 'good',      'Good match! A few improvements could make you stronger.'
        elif score_r >= 55: verdict, msg = 'moderate',  'Moderate match. Add suggested skills and metrics.'
        else:               verdict, msg = 'poor',      'Needs improvement. Focus on missing skills and achievements.'
        kw_suggestions = []
        tech = [k for k in list(missing)[:15] if k not in ['communication','leadership','teamwork']]
        soft = [k for k in list(missing)[:15] if k in ['communication','leadership','teamwork','collaboration']]
        if tech: kw_suggestions.append(f"Technical skills to add: {', '.join(tech[:6])}")
        if soft: kw_suggestions.append(f"Soft skills to highlight: {', '.join(soft[:4])}")
        return {
            'match_score':       score_r,
            'impact_score':      impact['impact_score'],
            'matching_keywords': list(matches)[:25],
            'missing_keywords':  list(missing)[:25],
            'total_matching':    len(matches),
            'total_missing':     len(missing),
            'total_impacts':     impact['total_impacts'],
            'impact_suggestions':impact['suggestions'][:4],
            'keyword_suggestions':kw_suggestions[:3],
            'verdict':           verdict,
            'verdict_message':   msg,
            'filename':          base + '.docx',
            'pdf_filename':      base + '.pdf',
            'name':              self.extract_name(resume_text),
        }


matcher = ResumeMatcher()


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resume Optimizer</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0d1117;
    --surface:  #161b22;
    --border:   #30363d;
    --primary:  #2f81f7;
    --primary2: #1a5fb4;
    --success:  #3fb950;
    --warning:  #d29922;
    --danger:   #f85149;
    --text:     #e6edf3;
    --muted:    #8b949e;
    --radius:   12px;
  }

  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 32px 20px 60px;
  }

  /* ── HEADER ── */
  .header {
    text-align: center;
    margin-bottom: 40px;
  }
  .header-badge {
    display: inline-block;
    background: linear-gradient(135deg, var(--primary), #6e40c9);
    color: #fff;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 4px 12px;
    border-radius: 20px;
    margin-bottom: 14px;
  }
  .header h1 {
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    font-weight: 700;
    background: linear-gradient(135deg, #e6edf3 0%, var(--primary) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 10px;
  }
  .header p {
    color: var(--muted);
    font-size: 15px;
  }

  /* ── MAIN GRID ── */
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    max-width: 1300px;
    margin: 0 auto 24px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    display: flex;
    flex-direction: column;
  }

  .card-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .8px;
    margin-bottom: 12px;
  }

  textarea {
    flex: 1;
    min-height: 440px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'Inter', monospace;
    font-size: 13px;
    line-height: 1.6;
    padding: 14px;
    resize: vertical;
    transition: border-color .2s;
  }
  textarea:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(47,129,247,.15);
  }
  textarea::placeholder { color: #484f58; }

  /* ── ANALYZE BUTTON ── */
  .btn-wrap {
    max-width: 1300px;
    margin: 0 auto 20px;
  }
  .btn-analyze {
    width: 100%;
    padding: 16px;
    background: linear-gradient(135deg, var(--primary) 0%, #6e40c9 100%);
    color: #fff;
    font-family: 'Inter', sans-serif;
    font-size: 16px;
    font-weight: 600;
    border: none;
    border-radius: var(--radius);
    cursor: pointer;
    transition: opacity .2s, transform .1s;
    letter-spacing: .3px;
  }
  .btn-analyze:hover { opacity: .9; transform: translateY(-1px); }
  .btn-analyze:active { transform: translateY(0); }
  .btn-analyze:disabled { opacity: .45; cursor: not-allowed; transform: none; }

  /* ── SPINNER ── */
  .spinner {
    display: none;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
    margin: 12px 0;
  }
  .spinner.show { display: block; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spin-icon {
    display: inline-block;
    width: 16px; height: 16px;
    border: 2px solid var(--border);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin .7s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
  }

  /* ── RESULTS ── */
  #results {
    display: none;
    max-width: 1300px;
    margin: 0 auto;
    animation: fadeUp .4s ease;
  }
  @keyframes fadeUp { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:none; } }

  /* Score hero */
  .score-hero {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 36px 24px;
    text-align: center;
    margin-bottom: 20px;
    position: relative;
    overflow: hidden;
  }
  .score-hero::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 0%, rgba(47,129,247,.12) 0%, transparent 70%);
    pointer-events: none;
  }
  .score-number {
    font-size: 72px;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 8px;
  }
  .score-label {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 10px;
  }
  .verdict-pill {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 30px;
    font-size: 13px;
    font-weight: 500;
    background: rgba(255,255,255,.07);
    color: var(--muted);
  }

  .c-excellent { color: var(--success); }
  .c-good      { color: #56d364; }
  .c-moderate  { color: var(--warning); }
  .c-poor      { color: var(--danger); }

  /* Stats row */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 14px;
    text-align: center;
  }
  .stat-val {
    font-size: 30px;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 4px;
  }
  .stat-lbl { font-size: 12px; color: var(--muted); }

  /* Info panels */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    margin-bottom: 14px;
  }
  .panel-title {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .7px;
    color: var(--muted);
    margin-bottom: 12px;
  }
  .tag {
    display: inline-block;
    padding: 4px 11px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    margin: 4px 3px;
  }
  .tag-match   { background: rgba(63,185,80,.15);  color: #3fb950; border: 1px solid rgba(63,185,80,.3); }
  .tag-missing { background: rgba(210,153,34,.15); color: #d29922; border: 1px solid rgba(210,153,34,.3); }

  .suggestion-item {
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13.5px;
    line-height: 1.5;
    margin-bottom: 8px;
    border-left: 3px solid;
  }
  .suggestion-item.high   { background: rgba(248,81,73,.08);  border-color: var(--danger);  color: #ffb3af; }
  .suggestion-item.medium { background: rgba(210,153,34,.08); border-color: var(--warning); color: #f0c040; }
  .suggestion-item.low    { background: rgba(63,185,80,.08);  border-color: var(--success); color: #7ee787; }

  /* Download buttons */
  .dl-row {
    display: flex;
    gap: 12px;
    justify-content: center;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  .dl-btn {
    padding: 12px 28px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    font-family: 'Inter', sans-serif;
    transition: opacity .2s, transform .1s;
    text-decoration: none;
    display: inline-block;
  }
  .dl-btn:hover { opacity: .85; transform: translateY(-1px); }
  .dl-btn.docx { background: var(--primary);  color: #fff; }
  .dl-btn.pdf  { background: #e63946; color: #fff; }

  @media (max-width: 768px) {
    .grid       { grid-template-columns: 1fr; }
    .stats-row  { grid-template-columns: 1fr 1fr; }
  }
</style>
</head>
<body>

<div class="header">
  <div class="header-badge">AI Powered</div>
  <h1>Resume Optimizer</h1>
  <p>Match your resume to any job description — improve keywords, metrics, and ATS score</p>
</div>

<div class="grid">
  <div class="card">
    <div class="card-label">📄 Your Resume</div>
    <textarea id="resumeText" placeholder="Paste your resume text here...&#10;&#10;Example:&#10;John Smith&#10;john@email.com | linkedin.com/in/johnsmith&#10;&#10;WORK EXPERIENCE&#10;Software Engineer | Company | 2020 – Present&#10;• Reduced API latency by 40%&#10;• Led team of 6 engineers..."></textarea>
  </div>
  <div class="card">
    <div class="card-label">💼 Job Description</div>
    <textarea id="jobText" placeholder="Paste the job description here...&#10;&#10;Example:&#10;Senior Software Engineer&#10;We are looking for an engineer with experience in Python, AWS, Docker, Kubernetes, and CI/CD pipelines..."></textarea>
  </div>
</div>

<div class="btn-wrap">
  <button class="btn-analyze" id="analyzeBtn" onclick="analyze()">
    Analyze &amp; Optimize Resume →
  </button>
  <div class="spinner" id="spinner"><span class="spin-icon"></span> Analyzing your resume...</div>
</div>

<div id="results"></div>

<script>
async function analyze() {
  const resume = document.getElementById('resumeText').value.trim();
  const job    = document.getElementById('jobText').value.trim();
  if (!resume || !job) { alert('Please paste both your resume and the job description.'); return; }

  const btn = document.getElementById('analyzeBtn');
  const spinner = document.getElementById('spinner');
  btn.disabled = true;
  btn.textContent = 'Analyzing...';
  spinner.classList.add('show');
  document.getElementById('results').style.display = 'none';

  const fd = new FormData();
  fd.append('resume_text', resume);
  fd.append('job_text', job);

  try {
    const res = await fetch('/analyze', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Error'); return; }
    renderResults(data);
  } catch(e) {
    alert('Error: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Analyze & Optimize Resume →';
    spinner.classList.remove('show');
  }
}

function renderResults(d) {
  const vLabel = {
    excellent: '🏆 Excellent Match',
    good:      '✅ Good Match',
    moderate:  '⚠️ Moderate Match',
    poor:      '❌ Needs Improvement'
  }[d.verdict];

  const impactHtml = d.impact_suggestions.map((s, i) => {
    const cls = i < 2 ? 'high' : i < 3 ? 'medium' : 'low';
    return `<div class="suggestion-item ${cls}">${i+1}. ${s}</div>`;
  }).join('');

  const kwHtml = d.keyword_suggestions.map((s, i) => {
    const cls = i === 0 ? 'high' : 'medium';
    return `<div class="suggestion-item ${cls}">${s}</div>`;
  }).join('');

  const matchTags   = d.matching_keywords.map(k => `<span class="tag tag-match">${k}</span>`).join('');
  const missingTags = d.missing_keywords.map(k => `<span class="tag tag-missing">${k}</span>`).join('');

  document.getElementById('results').innerHTML = `
    <div class="score-hero">
      <div class="score-number c-${d.verdict}">${d.match_score}%</div>
      <div class="score-label c-${d.verdict}">${vLabel}</div>
      <div class="verdict-pill">${d.verdict_message}</div>
    </div>

    <div class="stats-row">
      <div class="stat-card"><div class="stat-val">${d.total_matching}</div><div class="stat-lbl">Keywords Matched</div></div>
      <div class="stat-card"><div class="stat-val">${d.total_missing}</div><div class="stat-lbl">Skills to Add</div></div>
      <div class="stat-card"><div class="stat-val">${d.impact_score}</div><div class="stat-lbl">Impact Score /100</div></div>
      <div class="stat-card"><div class="stat-val">${d.total_impacts}</div><div class="stat-lbl">Achievements Found</div></div>
    </div>

    ${impactHtml || kwHtml ? `
    <div class="panel">
      <div class="panel-title">Priority Improvements</div>
      ${impactHtml}${kwHtml}
    </div>` : ''}

    <div class="panel">
      <div class="panel-title">✅ Keywords Matched (${d.matching_keywords.length})</div>
      ${matchTags || '<span style="color:var(--muted)">None detected</span>'}
    </div>

    <div class="panel">
      <div class="panel-title">✨ Keywords Added to Resume (${d.missing_keywords.length})</div>
      ${missingTags || '<span style="color:var(--muted)">None — great job!</span>'}
    </div>

    <div class="panel" style="text-align:center;">
      <div class="panel-title" style="text-align:center;">Download Optimized Resume</div>
      <p style="color:var(--muted);font-size:13px;margin-bottom:16px;">
        Candidate: <strong style="color:var(--text)">${d.name}</strong>
      </p>
      <div class="dl-row">
        <a class="dl-btn docx" href="/download/${encodeURIComponent(d.filename)}">📄 Download Word (.docx)</a>
        <a class="dl-btn pdf"  href="/download/${encodeURIComponent(d.pdf_filename)}">📕 Download PDF</a>
      </div>
    </div>
  `;
  document.getElementById('results').style.display = 'block';
  document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
</script>
</body>
</html>'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        resume_text = request.form.get('resume_text', '')
        job_text    = request.form.get('job_text', '')
        if not resume_text or not job_text:
            return jsonify({'error': 'Please provide both resume and job description'}), 400
        results = matcher.analyze(resume_text, job_text)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<path:filename>')
def download_file(filename):
    path = os.path.join(app.config['OPTIMIZED_FOLDER'], filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    mime = 'application/pdf' if filename.endswith('.pdf') else \
           'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return send_file(path, as_attachment=True, download_name=filename, mimetype=mime)


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  RESUME OPTIMIZER")
    print("="*60)
    print("\n  Running at: http://localhost:5000\n")
    app.run(debug=True, host='127.0.0.1', port=5000)