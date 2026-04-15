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
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

# Download required NLTK data
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

# Industry skill synonyms for better matching
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
    'problem-solving': ['analytical', 'debugging', 'troubleshooting', 'optimization'],
    'machine learning': ['ml', 'ai', 'deep learning', 'neural networks', 'tensorflow', 'pytorch'],
    'data analysis': ['analytics', 'data science', 'visualization', 'tableau', 'power bi'],
    'cloud': ['azure', 'gcp', 'google cloud', 'serverless', 'cloud computing'],
    'devops': ['sre', 'site reliability', 'infrastructure', 'automation', 'terraform'],
    'frontend': ['ui', 'user interface', 'html', 'css', 'reactjs', 'vuejs'],
    'backend': ['server-side', 'api', 'rest', 'graphql', 'microservices'],
    'testing': ['qa', 'quality assurance', 'unit testing', 'integration testing', 'selenium'],
}

# Weighted keywords by importance
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

    def extract_skills_with_synonyms(self, text):
        """Extract skills including their synonyms for better matching"""
        text_lower = text.lower()
        skills = set()

        # Extract base keywords
        base_keywords = set(self.preprocess_text(text))
        skills.update(base_keywords)

        # Add synonyms for found skills
        for skill, synonyms in SKILL_SYNONYMS.items():
            if skill in text_lower or any(syn in text_lower for syn in synonyms):
                skills.add(skill)
                skills.update(synonyms)

        # Extract multi-word technical terms
        multi_word_patterns = [
            r'machine\s+learning', r'deep\s+learning', r'neural\s+network',
            r'natural\s+language\s+processing', r'computer\s+vision',
            r'rest(?!ful)\s*api', r'graphql', r'microservice',
            r'continuous\s+integration', r'continuous\s+deployment',
            r'site\s+reliability', r'serverless\s+architecture',
            r'data\s+structure', r'object\s+oriented', r'agile\s+methodolog',
            r'test\s+driven\s+development', r'behavior\s+driven\s+development'
        ]

        for pattern in multi_word_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                skills.add(match.replace(' ', '_'))

        return skills
    
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
        """Generate specific, actionable suggestions for adding quantified impacts"""
        suggestions = []

        # Priority 1: Percentages (most impactful for ATS)
        if metrics_count['percentages'] < 2:
            suggestions.append("Add percentage improvements to show scale of impact (e.g., 'Increased efficiency by 35%', 'Reduced error rate by 60%')")

        # Priority 2: Financial impact (highly valued by employers)
        if metrics_count['currency'] == 0:
            suggestions.append("Include dollar amounts to demonstrate business value (e.g., 'Saved $50,000 annually', 'Generated $1.2M in revenue', 'Managed $500K budget')")

        # Priority 3: Time-based metrics (shows efficiency)
        if metrics_count['time_based'] < 2:
            suggestions.append("Add time-based achievements (e.g., 'Reduced processing time from 4 hours to 30 minutes', 'Delivered project 2 weeks ahead of schedule')")

        # Priority 4: Strong action verbs
        if metrics_count['action_verbs'] < 5:
            suggestions.append("Start bullet points with strong action verbs: 'Led', 'Architected', 'Optimized', 'Transformed', 'Pioneered', 'Accelerated'")

        # Priority 5: Role-specific metrics
        resume_lower = resume_text.lower()
        if any(kw in resume_lower for kw in ['software', 'developer', 'engineer', 'programming']):
            suggestions.append("For engineering roles: Add metrics like 'Code coverage increased from 60% to 90%', 'Reduced API response time by 200ms'")
        elif any(kw in resume_lower for kw in ['sales', 'business', 'account']):
            suggestions.append("For sales roles: Add metrics like 'Exceeded quota by 125%', 'Closed $2M in new business', 'Improved conversion rate by 18%'")
        elif any(kw in resume_lower for kw in ['marketing', 'digital', 'content']):
            suggestions.append("For marketing roles: Add metrics like 'Increased organic traffic by 150%', 'Generated 5,000+ qualified leads', 'ROI of 340% on ad spend'")
        elif any(kw in resume_lower for kw in ['manager', 'lead', 'director', 'head']):
            suggestions.append("For leadership roles: Add metrics like 'Managed team of 12', 'Oversaw $5M budget', 'Reduced turnover by 40%'")

        if not suggestions:
            suggestions.append("Excellent! Your resume has strong quantified impacts. Consider adding more specific metrics where possible.")

        return suggestions

    def generate_keyword_suggestions(self, missing_keywords, job_text):
        """Generate prioritized, actionable suggestions for missing keywords"""
        suggestions = []

        if not missing_keywords:
            return ["✅ All key skills from the job description are present in your resume!"]

        # Categorize missing keywords
        technical_skills = []
        soft_skills = []
        tools = []
        other = []

        soft_skill_keywords = ['communication', 'leadership', 'teamwork', 'collaboration', 'problem-solving',
                              'analytical', 'critical thinking', 'adaptability', 'time management', 'mentorship']

        tool_keywords = ['git', 'docker', 'kubernetes', 'jenkins', 'terraform', 'ansible', 'aws', 'azure',
                        'gcp', 'jira', 'confluence', 'slack', 'teams', 'vscode', 'intellij', 'eclipse']

        for keyword in list(missing_keywords)[:15]:
            kw_lower = keyword.lower()
            if any(sk in kw_lower for sk in soft_skill_keywords):
                soft_skills.append(keyword)
            elif any(tk in kw_lower for tk in tool_keywords):
                tools.append(keyword)
            else:
                technical_skills.append(keyword)

        # Generate prioritized suggestions
        if technical_skills:
            suggestions.append(f"📚 Technical Skills to add: {', '.join(technical_skills[:5])}")
        if tools:
            suggestions.append(f"🛠️ Tools/Platforms to mention: {', '.join(tools[:5])}")
        if soft_skills:
            suggestions.append(f"💬 Soft Skills to highlight: {', '.join(soft_skills[:3])}")

        return suggestions if suggestions else [f"✨ Consider incorporating: {', '.join(list(missing_keywords)[:8])}"]
    
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
        """Calculate match percentage with improved accuracy"""
        # Use enhanced skill extraction with synonyms
        resume_skills = self.extract_skills_with_synonyms(resume_text)
        job_skills = self.extract_skills_with_synonyms(job_text)

        if not job_skills:
            return 0, set(), set(), {}

        # Find matches
        matches = resume_skills.intersection(job_skills)

        # Weighted scoring - high value keywords count more
        weighted_match_score = 0
        weighted_job_total = 0

        for keyword in job_skills:
            weight = 1.5 if keyword in HIGH_WEIGHT_KEYWORDS else (1.2 if keyword in MEDIUM_WEIGHT_KEYWORDS else 1.0)
            weighted_job_total += weight
            if keyword in matches:
                weighted_match_score += weight

        # Calculate base percentage
        if weighted_job_total > 0:
            match_percentage = (weighted_match_score / weighted_job_total) * 100
        else:
            match_percentage = 0

        # Add impact quality score to overall match
        impact_analysis = self.analyze_impact_quality(resume_text)
        impact_bonus = impact_analysis['impact_score'] * 0.1  # Up to 10% bonus for good impacts

        # Add bonus for years of experience match
        experience_bonus = self.extract_experience_bonus(resume_text, job_text)

        final_score = min(100, match_percentage + impact_bonus + experience_bonus)

        return final_score, matches, job_skills - resume_skills, impact_analysis

    def extract_experience_bonus(self, resume_text, job_text):
        """Extract years of experience and give bonus if matched"""
        resume_exp = re.findall(r'(\d+)\s*(?:years?|yrs?|y\.?)\s*(?:of\s+)?(?:experience|exp\.?)', resume_text, re.IGNORECASE)
        job_exp = re.findall(r'(\d+)\s*(?:years?|yrs?|y\.?)\s*(?:of\s+)?(?:experience|exp\.?)', job_text, re.IGNORECASE)

        if resume_exp and job_exp:
            resume_years = int(max(resume_exp))
            job_years = int(min(job_exp))
            if resume_years >= job_years:
                return 5  # 5% bonus for meeting experience requirement

        return 0
    
    def extract_name_from_resume(self, text):
        """Extract name from resume with higher accuracy"""
        lines = text.strip().split('\n')

        # Priority 1: First non-empty line that looks like a name
        for line in lines[:5]:  # Check first 5 lines only
            line = line.strip()
            if not line:
                continue

            # Skip lines with contact info indicators
            if any(x in line.lower() for x in ['@', 'linkedin', 'github', 'http', 'www.', 'phone', 'mobile', '+']):
                continue

            # Skip lines that are clearly not names
            if any(x in line.lower() for x in ['experience', 'education', 'skills', 'work', 'summary', 'objective']):
                continue

            # Name should be relatively short and contain mostly letters
            if len(line) < 50 and len(line) > 2:
                # Check if it looks like a name (mostly letters and spaces)
                if re.match(r'^[A-Za-z\s\.]+$', line):
                    # Clean and format name
                    name = re.sub(r'[^\w\s]', '', line)
                    name = re.sub(r'\s+', ' ', name.strip())
                    # Convert to FirstName_LastName format
                    name_parts = name.split()
                    if len(name_parts) >= 2:
                        return f"{name_parts[0]}_{name_parts[-1]}"
                    elif len(name_parts) == 1:
                        return name_parts[0]

        # Priority 2: Look for name patterns in first 10 lines
        for line in lines[:10]:
            line = line.strip()
            # Pattern: Capitalized words that could be a name
            if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+', line) and len(line) < 40:
                if not any(x in line.lower() for x in ['@', 'linkedin', 'github']):
                    name = re.sub(r'[^\w\s]', '', line)
                    name = re.sub(r'\s+', '_', name.strip())
                    return name

        return "Candidate"

    def extract_name_for_display(self, text):
        """Extract full name for display purposes"""
        lines = text.strip().split('\n')

        for line in lines[:5]:
            line = line.strip()
            if not line:
                continue

            if any(x in line.lower() for x in ['@', 'linkedin', 'github', 'http', 'www.', 'phone', 'mobile', '+']):
                continue

            if any(x in line.lower() for x in ['experience', 'education', 'skills', 'work', 'summary', 'objective']):
                continue

            if len(line) < 50 and len(line) > 2:
                if re.match(r'^[A-Za-z\s\.]+$', line):
                    name = re.sub(r'[^\w\s]', '', line)
                    return re.sub(r'\s+', ' ', name.strip())

        return "Candidate"
    
    def extract_contact_info(self, text):
        """Extract contact info lines"""
        lines = text.strip().split('\n')
        for line in lines:
            if '@' in line or 'linkedin' in line.lower() or 'github' in line.lower():
                return line.strip()
        return ""
    
    def extract_job_role(self, job_text):
        """Extract job role from job description with improved accuracy"""
        lines = job_text.split('\n')[:30]

        # Comprehensive job role list
        job_roles = [
            'Software Engineer', 'Senior Software Engineer', 'Staff Software Engineer',
            'DevOps Engineer', 'Site Reliability Engineer', 'Data Scientist',
            'Product Manager', 'Project Manager', 'Frontend Developer', 'Backend Developer',
            'Full Stack Developer', 'Machine Learning Engineer', 'AI Engineer',
            'Cloud Engineer', 'Security Engineer', 'QA Engineer', 'Test Engineer',
            'SRE', 'System Administrator', 'Network Engineer', 'Database Administrator',
            'Business Analyst', 'Data Analyst', 'UX Designer', 'UI Designer',
            'Technical Lead', 'Engineering Manager', 'Architect', 'Solutions Architect',
            'Scrum Master', 'Agile Coach', 'Consultant', 'Developer'
        ]

        # Check first 10 lines for job title
        for line in lines[:10]:
            line_lower = line.lower()
            for role in job_roles:
                if role.lower() in line_lower:
                    clean_role = re.sub(r'[^\w\s]', '', role)
                    clean_role = re.sub(r'\s+', '_', clean_role.strip())
                    return clean_role

        # Fallback patterns
        title_patterns = [
            r'(?:Job Title|Position|Role|Title)[:\s]+([A-Za-z\s]+?(?:Engineer|Developer|Manager|Analyst|Specialist|Consultant|Architect|Lead|Director))',
            r'([A-Za-z\s]+?(?:Engineer|Developer|Manager|Analyst|Specialist|Consultant|Architect|Lead|Director))(?:\s+(?:-|:|required|needed))',
            r'we\s+are\s+(?:looking\s+for|hiring)\s+a\s+([A-Za-z\s]+?(?:Engineer|Developer|Manager|Analyst))',
            r'join\s+our\s+team\s+as\s+a\s+([A-Za-z\s]+?(?:Engineer|Developer|Manager|Analyst))'
        ]

        for pattern in title_patterns:
            match = re.search(pattern, job_text, re.IGNORECASE)
            if match:
                role = match.group(1).strip()
                # Clean up the role
                role = re.sub(r'\s+(and|&)\s+.*$', '', role)  # Remove "and other duties"
                role = re.sub(r'[^\w\s]', '', role)
                role = re.sub(r'\s+', '_', role.strip())
                if len(role) > 3:
                    return role

        # Last resort: use generic role based on key skills
        if 'python' in job_text.lower() or 'java' in job_text.lower():
            return 'Software_Developer'
        elif 'cloud' in job_text.lower() or 'aws' in job_text.lower():
            return 'Cloud_Engineer'
        elif 'data' in job_text.lower():
            return 'Data_Analyst'

        return 'Position'
    
    def generate_filename(self, resume_text, job_text):
        """Generate consistent filename: FirstName_LastName_JobRole_Date.docx"""
        full_name = self.extract_name_from_resume(resume_text)

        # Ensure name is properly formatted as FirstName_LastName
        # Replace any spaces with underscores and clean up
        full_name = re.sub(r'\s+', '_', full_name.strip())

        # If we have more than 2 parts, take first and last
        name_parts = full_name.split('_')
        if len(name_parts) >= 2:
            formatted_name = f"{name_parts[0]}_{name_parts[-1]}"
        elif len(name_parts) == 1 and name_parts[0]:
            formatted_name = name_parts[0]
        else:
            formatted_name = "Candidate"

        job_role = self.extract_job_role(job_text)

        # Use consistent date format
        date = datetime.now().strftime("%Y%m%d")

        # Build filename with consistent format
        filename = f"{formatted_name}_{job_role}_{date}.docx"

        # Clean up: remove multiple underscores, invalid characters
        filename = re.sub(r'_+', '_', filename)  # Replace multiple underscores with single
        filename = re.sub(r'^_|_$', '', filename)  # Remove leading/trailing underscores
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)  # Remove invalid filename characters

        # Ensure filename isn't too long (max 255 chars for most systems, but keep it reasonable)
        if len(filename) > 100:
            base, ext = os.path.splitext(filename)
            filename = f"{base[:95]}{ext}"

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
        """Create professionally formatted Word document with enhanced styling"""
        doc = Document()

        # Set professional page margins
        for section in doc.sections:
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)

        lines = text.split('\n')

        # Skip lines that are impact suggestions (they start with emoji or are in the KEY ACHIEVEMENTS section)
        skip_next_section = False
        name_added = False
        contact_added = False
        added_sections = set()

        for line in lines:
            line_stripped = line.strip()

            # Skip empty lines at the beginning
            if not line_stripped and not name_added:
                continue

            # Skip the KEY ACHIEVEMENTS suggestion section (it's meta-advice, not resume content)
            if 'KEY ACHIEVEMENTS & IMPACT METRICS' in line_stripped:
                skip_next_section = True
                continue
            if skip_next_section and ('Example impact statements' in line_stripped or line_stripped.startswith('•') and ('percentage' in line_stripped.lower() or 'financial' in line_stripped.lower())):
                continue
            if skip_next_section and line_stripped and not line_stripped.startswith('•') and not line_stripped.startswith('💡') and not line_stripped.startswith('📊') and not line_stripped.startswith('💰'):
                skip_next_section = False

            if skip_next_section:
                continue

            if not line_stripped:
                doc.add_paragraph()
                continue

            # Name line - centered, large, professional
            if not name_added and len(line_stripped) < 50 and not any(x in line_stripped.lower() for x in ['@', 'linkedin', 'github', '|', 'http', 'www.', 'phone', 'mobile', '+']):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(line_stripped)
                run.font.name = 'Calibri Light'
                run.font.size = Pt(28)
                run.font.bold = True
                run.font.color.rgb = RGBColor(30, 30, 30)
                name_added = True

                # Add subtle underline accent
                p_format = p.paragraph_format
                p_format.space_after = Pt(8)
                continue

            # Contact info - centered, smaller, gray
            if not contact_added and any(x in line_stripped.lower() for x in ['@', 'linkedin', 'github', 'http', 'www.', 'phone', 'mobile', '+']):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(line_stripped)
                run.font.name = 'Calibri'
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(100, 100, 100)
                contact_added = True
                p.paragraph_format.space_after = Pt(12)
                continue

            # Section headers - bold, colored, with spacing
            if line_stripped.isupper() and len(line_stripped) < 50 and line_stripped not in added_sections:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(16)
                p.paragraph_format.space_after = Pt(8)
                run = p.add_run(line_stripped)
                run.font.name = 'Calibri'
                run.font.size = Pt(14)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0, 77, 153)  # Professional blue
                run.font.underline = True
                added_sections.add(line_stripped)

                # Add a subtle line after section header
                line_p = doc.add_paragraph()
                line_p.paragraph_format.space_after = Pt(4)
                line_run = line_p.add_run('─' * 50)
                line_run.font.size = Pt(8)
                line_run.font.color.rgb = RGBColor(200, 200, 200)
                continue

            # Company/job subheaders
            if '|' in line_stripped or ' at ' in line_stripped.lower():
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(10)
                p.paragraph_format.space_after = Pt(4)
                run = p.add_run(line_stripped)
                run.font.name = 'Calibri'
                run.font.size = Pt(12)
                run.font.bold = True
                run.font.color.rgb = RGBColor(50, 50, 50)
                continue

            # Bullet points with enhanced formatting
            if line_stripped.startswith('•') or line_stripped.startswith('-') or line_stripped.startswith('*'):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.3)
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.line_spacing = 1.3
                bullet_text = line_stripped[1:].strip()

                # Create bullet with proper formatting
                run = p.add_run('•  ')
                run.font.size = Pt(11)

                # Add the bullet text with smart highlighting
                # First, check if it contains metrics
                has_metrics = bool(re.search(r'\d+%|\$\d+|\d+\s*(years?|months?|weeks|days?|hours?)', bullet_text, re.IGNORECASE))

                if has_metrics:
                    # Highlight the entire bullet in a slightly different color for emphasis
                    run = p.add_run(bullet_text)
                    run.font.name = 'Calibri'
                    run.font.size = Pt(11)
                    run.font.color.rgb = RGBColor(0, 100, 0)  # Dark green for achievement bullets
                    run.font.bold = True
                else:
                    run = p.add_run(bullet_text)
                    run.font.name = 'Calibri'
                    run.font.size = Pt(11)

                    # Highlight keywords within the bullet
                    words = bullet_text.split()
                    for i, word in enumerate(words):
                        clean_word = re.sub(r'[^\w]', '', word.lower())
                        if clean_word in HIGH_WEIGHT_KEYWORDS:
                            # Could add individual word highlighting here
                            pass
                continue

            # Skill categories (e.g., "Languages: Python, Java")
            if ':' in line_stripped and len(line_stripped.split(':')) == 2 and len(line_stripped) < 100:
                parts = line_stripped.split(':', 1)
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after = Pt(2)

                # Category label in bold
                run = p.add_run(parts[0].strip() + ': ')
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = RGBColor(60, 60, 60)

                # Skills in regular
                run = p.add_run(parts[1].strip())
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(80, 80, 80)
                continue

            # Regular paragraph text
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.3
            run = p.add_run(line_stripped)
            run.font.name = 'Calibri'
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(40, 40, 40)

        # Add impact analysis summary page if improvements were suggested
        if impact_analysis and impact_analysis.get('needs_improvement'):
            doc.add_page_break()

            # Header with icon
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run("📊 IMPACT METRICS ANALYSIS")
            run.font.name = 'Calibri'
            run.font.size = Pt(20)
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 100, 0)
            p.paragraph_format.space_after = Pt(16)

            # Score card with visual styling
            score_p = doc.add_paragraph()
            score_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            score_p.paragraph_format.space_after = Pt(16)

            score_value = impact_analysis['impact_score']
            score_color = RGBColor(0, 180, 0) if score_value >= 70 else (RGBColor(255, 180, 0) if score_value >= 40 else RGBColor(255, 80, 0))

            run = score_p.add_run(f"Impact Score: {score_value}/100")
            run.font.name = 'Calibri'
            run.font.size = Pt(18)
            run.font.bold = True
            run.font.color.rgb = score_color

            # Divider line
            divider = doc.add_paragraph()
            divider.alignment = WD_ALIGN_PARAGRAPH.CENTER
            divider_run = divider.add_run('─' * 40)
            divider_run.font.size = Pt(10)
            divider_run.font.color.rgb = RGBColor(200, 200, 200)
            divider.paragraph_format.space_after = Pt(16)

            # Suggestions header
            p = doc.add_paragraph()
            run = p.add_run("🎯 Priority Improvements:")
            run.font.name = 'Calibri'
            run.font.size = Pt(14)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0, 100, 150)
            p.paragraph_format.space_after = Pt(10)

            # Numbered suggestions with priority icons
            for i, suggestion in enumerate(impact_analysis['suggestions'][:5], 1):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.2)
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after = Pt(4)

                # Priority indicator
                priority = "🔴" if i <= 2 else "🟡" if i <= 4 else "🟢"
                run = p.add_run(f"{priority} {i}. {suggestion}")
                run.font.name = 'Calibri'
                run.font.size = Pt(11)

            # Example impact statements box
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(16)
            run = p.add_run("💡 Example Impact Statements:")
            run.font.name = 'Calibri'
            run.font.size = Pt(13)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0, 100, 150)

            examples = [
                "Increased system performance by 45% through code optimization",
                "Reduced cloud infrastructure costs by $75,000 annually",
                "Led team of 5 developers to deliver project 3 weeks early",
                "Improved customer satisfaction score from 82% to 96%",
                "Automated deployment process, saving 20 hours per week"
            ]

            for example in examples:
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.4)
                p.paragraph_format.space_before = Pt(2)
                run = p.add_run(f"→ {example}")
                run.font.name = 'Calibri'
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(100, 100, 100)
                run.font.italic = True

        doc.save(output_path)

    def create_beautiful_pdf(self, text, output_path, impact_analysis=None):
        """Create professionally formatted PDF document with enhanced styling"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Container for the 'Flowable' objects
        story = []

        # Define custom styles
        styles = getSampleStyleSheet()

        # Name style - large, centered, bold
        name_style = ParagraphStyle(
            'CustomName',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        # Contact info style
        contact_style = ParagraphStyle(
            'Contact',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#666666'),
            spaceAfter=16,
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )

        # Section header style - highlighted background
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#ffffff'),
            spaceBefore=16,
            spaceAfter=8,
            fontName='Helvetica-Bold',
            backColor=colors.HexColor('#004d99'),
            leftIndent=0,
            rightIndent=0,
            firstLineIndent=0,
            padding=6
        )

        # Subheader style (company/job info)
        subheader_style = ParagraphStyle(
            'Subheader',
            parent=styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#333333'),
            spaceBefore=10,
            spaceAfter=4,
            fontName='Helvetica-Bold'
        )

        # Bullet point style
        bullet_style = ParagraphStyle(
            'Bullet',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#282828'),
            spaceBefore=3,
            spaceAfter=3,
            leftIndent=24,
            firstLineIndent=-12,
            fontName='Helvetica'
        )

        # Bullet with metrics highlighted
        bullet_metric_style = ParagraphStyle(
            'BulletMetric',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#006400'),
            spaceBefore=3,
            spaceAfter=3,
            leftIndent=24,
            firstLineIndent=-12,
            fontName='Helvetica-Bold'
        )

        # Regular paragraph style
        para_style = ParagraphStyle(
            'CustomPara',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#282828'),
            spaceBefore=2,
            spaceAfter=2,
            fontName='Helvetica',
            leading=14
        )

        # Skill category style
        skill_style = ParagraphStyle(
            'Skill',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#505050'),
            spaceBefore=4,
            spaceAfter=2,
            fontName='Helvetica'
        )

        lines = text.split('\n')

        # Skip meta-advice sections
        skip_next_section = False
        name_added = False
        contact_added = False

        for line in lines:
            line_stripped = line.strip()

            if not line_stripped and not name_added:
                continue

            # Skip KEY ACHIEVEMENTS suggestion section
            if 'KEY ACHIEVEMENTS & IMPACT METRICS' in line_stripped:
                skip_next_section = True
                continue
            if skip_next_section and ('Example impact statements' in line_stripped or
                (line_stripped.startswith('•') and any(x in line_stripped.lower()
                for x in ['percentage', 'financial', 'time-based', 'action verbs']))):
                continue
            if skip_next_section and line_stripped and not line_stripped.startswith('•') \
                and not any(line_stripped.startswith(e) for e in ['💡', '📊', '💰', '⏱️', '⚡']):
                skip_next_section = False

            if skip_next_section:
                continue

            if not line_stripped:
                story.append(Spacer(1, 0.1*inch))
                continue

            # Name line
            if not name_added and len(line_stripped) < 50 and \
                not any(x in line_stripped.lower() for x in ['@', 'linkedin', 'github', '|', 'http', 'www.', 'phone', 'mobile', '+']):
                story.append(Paragraph(line_stripped, name_style))
                name_added = True
                continue

            # Contact info
            if not contact_added and any(x in line_stripped.lower() for x in ['@', 'linkedin', 'github', 'http', 'www.', 'phone', 'mobile', '+']):
                story.append(Paragraph(line_stripped, contact_style))
                contact_added = True
                continue

            # Section headers - with highlighted background
            if line_stripped.isupper() and len(line_stripped) < 50:
                story.append(Paragraph(line_stripped, header_style))
                continue

            # Company/job subheaders
            if '|' in line_stripped or ' at ' in line_stripped.lower():
                story.append(Paragraph(line_stripped, subheader_style))
                continue

            # Bullet points
            if line_stripped.startswith('•') or line_stripped.startswith('-') or line_stripped.startswith('*'):
                bullet_text = line_stripped[1:].strip()
                has_metrics = bool(re.search(r'\d+%|\$\d+|\d+\s*(years?|months?|weeks|days?|hours?)', bullet_text, re.IGNORECASE))

                if has_metrics:
                    story.append(Paragraph(f"•  {bullet_text}", bullet_metric_style))
                else:
                    story.append(Paragraph(f"•  {bullet_text}", bullet_style))
                continue

            # Skill categories
            if ':' in line_stripped and len(line_stripped.split(':')) == 2 and len(line_stripped) < 100:
                parts = line_stripped.split(':', 1)
                story.append(Paragraph(f"<b>{parts[0].strip()}:</b> {parts[1].strip()}", skill_style))
                continue

            # Regular paragraph
            story.append(Paragraph(line_stripped, para_style))

        # Add impact analysis page if needed
        if impact_analysis and impact_analysis.get('needs_improvement'):
            story.append(PageBreak())

            # Impact header
            impact_header_style = ParagraphStyle(
                'ImpactHeader',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#ff6600'),
                spaceAfter=16,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph("📊 IMPACT METRICS ANALYSIS", impact_header_style))

            # Score
            score_value = impact_analysis['impact_score']
            score_color = '#00b400' if score_value >= 70 else ('#ffb600' if score_value >= 40 else '#ff5000')
            score_style = ParagraphStyle(
                'Score',
                parent=styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor(score_color),
                spaceAfter=16,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph(f"Impact Score: {score_value}/100", score_style))

            # Divider
            story.append(Spacer(1, 0.2*inch))

            # Suggestions header
            suggestion_header_style = ParagraphStyle(
                'SuggestionHeader',
                parent=styles['Heading3'],
                fontSize=13,
                textColor=colors.HexColor('#006496'),
                spaceAfter=10,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph("🎯 Priority Improvements:", suggestion_header_style))

            # Suggestions
            for i, suggestion in enumerate(impact_analysis['suggestions'][:5], 1):
                priority_symbol = "🔴" if i <= 2 else ("🟡" if i <= 4 else "🟢")
                story.append(Paragraph(f"{priority_symbol} {i}. {suggestion}", para_style))

            # Example statements
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("💡 Example Impact Statements:", suggestion_header_style))

            examples = [
                "Increased system performance by 45% through code optimization",
                "Reduced cloud infrastructure costs by $75,000 annually",
                "Led team of 5 developers to deliver project 3 weeks early",
                "Improved customer satisfaction score from 82% to 96%",
                "Automated deployment process, saving 20 hours per week"
            ]

            example_style = ParagraphStyle(
                'Example',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#666666'),
                spaceBefore=2,
                leftIndent=36,
                fontName='Helvetica-Oblique'
            )

            for example in examples:
                story.append(Paragraph(f"→ {example}", example_style))

        # Build the PDF
        doc.build(story)

        # Save to file
        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())
        buffer.close()

    def analyze(self, resume_text, job_text):
        """Main analysis with quantified impact and clear feedback"""
        match_score, matching_keywords, missing_keywords, impact_analysis = self.calculate_match_score(resume_text, job_text)

        # Generate clear, prioritized suggestions
        keyword_suggestions = self.generate_keyword_suggestions(missing_keywords, job_text)

        # Add missing keywords to resume
        optimized_resume = self.add_missing_keywords(resume_text, missing_keywords)

        # Add quantified impact suggestions if needed
        if impact_analysis['needs_improvement']:
            optimized_resume = self.add_quantified_impacts(optimized_resume, impact_analysis)

        # Generate base filename
        base_filename = self.generate_filename(resume_text, job_text)

        # Save to Word with beautiful formatting
        docx_filename = base_filename.replace('.docx', '.docx')
        docx_path = os.path.join(app.config['OPTIMIZED_FOLDER'], docx_filename)
        self.create_beautiful_word(optimized_resume, docx_path, impact_analysis)

        # Save to PDF with beautiful formatting
        pdf_filename = base_filename.replace('.docx', '.pdf')
        pdf_path = os.path.join(app.config['OPTIMIZED_FOLDER'], pdf_filename)
        self.create_beautiful_pdf(optimized_resume, pdf_path, impact_analysis)

        # Extract name for display
        name = self.extract_name_for_display(resume_text)

        # Determine verdict with clearer thresholds
        if match_score >= 85:
            verdict = 'excellent'
            verdict_message = "Excellent match! Your resume is well-aligned with this job."
        elif match_score >= 70:
            verdict = 'good'
            verdict_message = "Good match! A few improvements could make you a stronger candidate."
        elif match_score >= 55:
            verdict = 'moderate'
            verdict_message = "Moderate match. Consider adding the suggested skills and metrics."
        else:
            verdict = 'poor'
            verdict_message = "Needs improvement. Focus on adding missing skills and quantified achievements."

        return {
            'match_score': round(match_score, 1),
            'impact_score': impact_analysis['impact_score'],
            'matching_keywords': list(matching_keywords)[:25],
            'missing_keywords': list(missing_keywords)[:25],
            'total_matching': len(matching_keywords),
            'total_missing': len(missing_keywords),
            'total_impacts': impact_analysis['total_impacts'],
            'impact_suggestions': impact_analysis['suggestions'][:5],
            'keyword_suggestions': keyword_suggestions[:4],
            'verdict': verdict,
            'verdict_message': verdict_message,
            'filename': docx_filename,
            'pdf_filename': pdf_filename,
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
            margin-right: 10px;
        }

        .download-btn.pdf {
            background: #f44336;
        }

        .download-container {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
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

        .suggestion-box {
            background: linear-gradient(135deg, #fff5e6 0%, #ffe0b2 100%);
            border-left: 4px solid #ff9800;
            padding: 15px;
            margin: 15px 0;
            border-radius: 5px;
        }

        .suggestion-box h4 {
            color: #e65100;
            margin-bottom: 10px;
            font-size: 14px;
        }

        .suggestion-item {
            padding: 8px 0;
            border-bottom: 1px solid rgba(0,0,0,0.1);
            font-size: 13px;
        }

        .suggestion-item:last-child {
            border-bottom: none;
        }

        .priority-high {
            color: #d32f2f;
            font-weight: 600;
        }

        .priority-medium {
            color: #f57c00;
            font-weight: 500;
        }

        .priority-low {
            color: #388e3c;
        }

        .verdict-message {
            background: rgba(255,255,255,0.15);
            padding: 10px 20px;
            border-radius: 25px;
            display: inline-block;
            margin-top: 10px;
            font-size: 14px;
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
            ✨ AI-Powered: Keyword matching + Impact analysis + Smart suggestions for higher selection chances
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
                'excellent': '🏆 EXCELLENT MATCH',
                'good': '✅ GOOD MATCH',
                'moderate': '⚠️ MODERATE MATCH',
                'poor': '❌ NEEDS IMPROVEMENT'
            }[data.verdict];

            const verdictMessage = data.verdict_message || '';

            // Build impact suggestions HTML
            let impactHtml = '';
            if (data.impact_suggestions && data.impact_suggestions.length > 0) {
                impactHtml = '<div class="suggestion-box"><h4>📊 Priority Improvements for Higher Selection Chance:</h4>';
                data.impact_suggestions.forEach((suggestion, idx) => {
                    const priorityClass = idx < 2 ? 'priority-high' : (idx < 4 ? 'priority-medium' : 'priority-low');
                    impactHtml += `<div class="suggestion-item ${priorityClass}">${idx + 1}. ${suggestion}</div>`;
                });
                impactHtml += '</div>';
            }

            // Build keyword suggestions HTML
            let keywordSuggestionHtml = '';
            if (data.keyword_suggestions && data.keyword_suggestions.length > 0) {
                keywordSuggestionHtml = '<div class="keywords"><h4 style="margin-bottom:10px;color:#333;">🎯 Skills to Add:</h4>';
                data.keyword_suggestions.forEach(suggestion => {
                    keywordSuggestionHtml += `<div class="impact-suggestion">${suggestion}</div>`;
                });
                keywordSuggestionHtml += '</div>';
            }

            const html = `
                <div class="score-card">
                    <div class="score-number">${data.match_score}%</div>
                    <div class="${verdictClass}" style="font-size: 22px; font-weight:bold;">${verdictText}</div>
                    ${verdictMessage ? `<div class="verdict-message">${verdictMessage}</div>` : ''}
                    <div style="font-size: 14px; margin-top: 10px; opacity:0.9;">📈 Impact Score: ${data.impact_score || 0}/100</div>
                </div>

                <div class="stats">
                    <div class="stat">
                        <div class="stat-number">${data.total_matching}</div>
                        <div>Keywords Matched</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">${data.total_missing}</div>
                        <div>Skills to Add</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">${data.total_impacts || 0}</div>
                        <div>Quantified Achievements</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number" style="font-size:20px;">${data.name}</div>
                        <div>Candidate</div>
                    </div>
                </div>

                ${impactHtml}
                ${keywordSuggestionHtml}

                <div class="keywords">
                    <strong>✅ Keywords found in your resume (${data.matching_keywords.length}):</strong><br>
                    ${data.matching_keywords.map(k => `<span class="tag tag-matching">${k}</span>`).join('') || 'None'}
                </div>

                <div class="keywords">
                    <strong>✨ Keywords added to optimize (${data.missing_keywords.length}):</strong><br>
                    ${data.missing_keywords.map(k => `<span class="tag tag-missing">${k}</span>`).join('') || 'None'}
                </div>

                <div style="text-align: center; margin-top: 25px;">
                    <p style="background:#e8f5e9; padding:12px; border-radius:8px; display:inline-block;">
                        ✅ <strong>Optimized resume ready!</strong><br>
                        <span style="color:#666; font-size:13px;">${data.name}_${data.verdict.toUpperCase()}_Match</span>
                    </p>
                    <div class="download-container">
                        <button class="download-btn" onclick="window.location.href='/download/' + encodeURIComponent('${data.filename}')">
                            📄 Download Word (.docx)
                        </button>
                        <button class="download-btn pdf" onclick="window.location.href='/download/' + encodeURIComponent('${data.pdf_filename}')">
                            📕 Download PDF
                        </button>
                    </div>
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
        # Determine MIME type based on file extension
        if filename.endswith('.pdf'):
            mimetype = 'application/pdf'
        else:
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
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