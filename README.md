# Kenya Job Scraper v19 - Enhanced Production Version

![Python](https://img.shields.io/badge/python-v3.6+-blue.svg)
![Selenium](https://img.shields.io/badge/selenium-4.0+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Status](https://img.shields.io/badge/status-production-brightgreen.svg)

## 🇰🇪 Overview

Kenya Job Scraper v19 is a comprehensive, production-grade web scraper designed specifically to collect data analytics, statistics, and business intelligence job listings from major Kenyan job boards. This enhanced version features advanced human verification handling, intelligent caching, and an interactive dashboard for data visualization.
<img width="1832" height="864" alt="image" src="https://github.com/user-attachments/assets/737208d5-a5ee-415f-ac91-870aa5044d76" />

### 🎯 Target Job Categories
- Data Analytics & Data Science
- Statistics & Statistical Analysis
- Business Intelligence & Reporting
- Monitoring & Evaluation (M&E)
- Research Analysis
- Data Engineering

### 🌐 Supported Job Boards
- **MyJobMag Kenya** (Primary source)
- **BrighterMonday Kenya**
- **Fuzu Kenya** (Enhanced human verification)
- **CareerPoint Kenya**
- **MyJobsInKenya**
<img width="1750" height="883" alt="image" src="https://github.com/user-attachments/assets/add191ab-7324-45b5-afd7-56aa131611b1" />

## ✨ Key Features

### 🚀 Advanced Scraping Capabilities
- **Multi-source Scraping**: Simultaneously scrapes 5+ major Kenyan job boards
- **Smart Keyword Matching**: Configurable keyword system for targeted job discovery
- **Date-based Filtering**: Automatically filters jobs based on posting and expiry dates
- **Duplicate Detection**: Prevents duplicate job entries across sources

### 🧠 Intelligent Systems
- **Enhanced Human Verification**: Advanced handling for Cloudflare and similar challenges
- **Smart Cache Management**: Configuration-based cache invalidation system
- **Error Recovery**: Robust error handling with automatic retry mechanisms
- **Popup Handling**: Comprehensive popup and cookie consent management

### 📊 Data Output & Visualization
- **Multiple Formats**: JSON, CSV, and HTML dashboard outputs
- **Interactive Dashboard**: Real-time charts, filtering, and export capabilities
- **Comprehensive Logging**: Detailed operation logs for debugging and monitoring
- **Data Validation**: Ensures data quality and consistency

### ⚡ Performance Features
- **Lazy Driver Loading**: WebDriver initialized only when needed
- **Optimized Pagination**: Smart pagination based on job dates
- **Concurrent Processing**: Efficient handling of multiple job sources
- **Resource Management**: Automatic cleanup and memory management

## 📋 Requirements

### System Requirements
- **Operating System**: Windows 10+, macOS 10.14+, or Linux
- **Python**: 3.6 or higher
- **Chrome Browser**: Latest stable version
- **Memory**: Minimum 4GB RAM recommended
- **Storage**: At least 100MB free space for data and logs

### Python Dependencies
```
selenium>=4.0.0
beautifulsoup4>=4.9.0
pandas>=1.3.0
requests>=2.25.0
lxml>=4.6.0
```

### WebDriver Requirements
- Chrome WebDriver (automatically managed by Selenium 4.0+)
- Compatible with your Chrome browser version

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/kenya-job-scraper.git
cd kenya-job-scraper
```

### 2. Create Virtual Environment (Recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create Requirements File
If not provided, create `requirements.txt`:
```txt
selenium>=4.0.0
beautifulsoup4>=4.9.0
pandas>=1.3.0
requests>=2.25.0
lxml>=4.6.0
```

## 🚀 Quick Start

### Basic Usage
```python
from kenya_job_scraper import KenyaJobScraper

# Initialize scraper with custom path
scraper = KenyaJobScraper(save_path="C:/MyJobs/")

# Run the scraper
scraper.run()
```

### Command Line Usage
```bash
python kenya_job_scraper.py
```

## ⚙️ Configuration

### Search Keywords Configuration
Modify the `search_keywords` list in the `__init__` method:

```python
self.search_keywords = [
    "data analyst",
    "data science",
    "business intelligence",
    "statistics",
    "monitoring and evaluation",
    # Add your custom keywords here
]
```

### File Path Configuration
```python
# Default path
save_path = "C:\\Users\\USER\\Documents\\app\\Jobs\\"

# Custom path
scraper = KenyaJobScraper(save_path="your/custom/path/")
```

### Cache Configuration
The scraper uses intelligent caching based on:
- Search keywords configuration
- Date changes
- Script version updates

## 📁 Output Files

### Generated Files (Daily)
- `kenya_jobs_YYYY-MM-DD.json` - Complete job data in JSON format
- `jobs_YYYY-MM-DD.csv` - Structured data for analysis
- `jobs_dashboard_YYYY-MM-DD.html` - Interactive visualization dashboard
- `cache_YYYY-MM-DD.pkl` - Cache file for performance optimization
- `job_scraper_YYYYMMDD_HHMMSS.log` - Detailed operation logs

### Dashboard Features
- **Interactive Charts**: Source distribution and location analysis
<img width="798" height="810" alt="image" src="https://github.com/user-attachments/assets/92084f3f-8f70-4178-aa01-229f927a6d55" />

- **Advanced Filtering**: By source, location, and keywords
<img width="1755" height="363" alt="image" src="https://github.com/user-attachments/assets/2bea4b86-67c2-4fc5-b376-4e8b3d1d4676" />

<img width="1750" height="883" alt="image" src="https://github.com/user-attachments/assets/c673add0-dfb5-4af8-b517-a44c65d9220a" />

- **Real-time Search**: Dynamic job title filtering
- **Export Functionality**: CSV export with current filters
- **Responsive Design**: Works on desktop and mobile devices
<img width="1770" height="848" alt="image" src="https://github.com/user-attachments/assets/b2867460-117b-459f-a84b-faf508269fc0" />


## 🔍 Usage Examples

### Example 1: Basic Scraping
```python
scraper = KenyaJobScraper()
scraper.run()
```

### Example 2: Custom Configuration
```python
# Custom save path and keywords
scraper = KenyaJobScraper(save_path="/home/user/jobs/")
scraper.search_keywords = ["python", "machine learning", "sql"]
scraper.run()
```

### Example 3: Dashboard Only
```python
scraper = KenyaJobScraper()
scraper.load_existing_data()  # Load existing data
scraper.generate_dashboard()  # Generate dashboard only
```

## 🛠️ Advanced Features

### Smart Caching System
- **Configuration-based**: Cache invalidates when keywords or settings change
- **Date-based**: Automatic daily cache refresh
- **Selective Caching**: Individual source caching for optimal performance

### Human Verification Handling
- **Cloudflare Challenge**: Advanced handling for Fuzu and similar sites
- **Extended Wait Times**: Up to 45 seconds for verification completion
- **Multiple Retry Attempts**: 3 attempts with different strategies
- **Visual Browser Mode**: Allows manual intervention when needed

### Error Recovery Mechanisms
- **Graceful Degradation**: Continues operation even if one source fails
- **Retry Logic**: Automatic retries for transient failures
- **Comprehensive Logging**: Detailed error tracking and debugging information
- **Resource Cleanup**: Automatic WebDriver and resource management

## 📊 Data Schema

### Job Record Structure
```json
{
  "job_title": "Data Analyst",
  "link": "https://example.com/job/123",
  "date_posted": "2025-07-28",
  "date_expires": "2025-08-15",
  "qualification": "Bachelor's Degree",
  "years_of_experience": "2-3 years",
  "location": "Nairobi, Kenya",
  "source": "MyJobMag Kenya"
}
```

## 🐛 Troubleshooting

### Common Issues

#### WebDriver Issues
```bash
# Error: ChromeDriver not found
# Solution: Update Chrome and restart
pip install --upgrade selenium
```

#### Human Verification Failures
- Ensure Chrome browser is visible (not headless)
- Check internet connection stability
- Manually complete verification if needed

#### Memory Issues
- Close other applications
- Increase system virtual memory
- Use smaller keyword lists for large-scale scraping

### Debug Mode
Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📈 Performance Optimization

### Best Practices
1. **Keyword Optimization**: Use specific, relevant keywords
2. **Time Scheduling**: Run during off-peak hours for better performance
3. **Resource Management**: Close unnecessary applications
4. **Regular Updates**: Keep dependencies and Chrome browser updated

### Performance Metrics
- **Jobs per minute**: ~15-25 jobs/minute (varies by source)
- **Memory usage**: ~200-400MB during operation
- **Cache hit rate**: ~70-80% on subsequent runs

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### Types of Contributions
- 🐛 Bug fixes and error handling improvements
- ✨ New job board integrations
- 📚 Documentation and examples
- 🔧 Performance optimizations
- 🎨 Dashboard enhancements

### Development Setup
1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test thoroughly
4. Submit a pull request with detailed description

### Coding Standards
- Follow PEP 8 style guidelines
- Add comprehensive docstrings
- Include error handling for new features
- Update tests for modified functionality

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support


### FAQ

**Q: How often should I run the scraper?**
A: Daily runs are recommended for fresh job listings. The cache system optimizes subsequent runs.

**Q: Can I add custom job boards?**
A: Yes! Follow the existing scraping methods as templates and submit a pull request.

**Q: What if human verification fails repeatedly?**
A: Try running during different times, ensure stable internet, or complete verification manually.

## 🔮 Roadmap

### Upcoming Features
- [ ] Email notifications for new jobs
- [ ] API integration for job applications
- [ ] Machine learning job relevance scoring
- [ ] Mobile app companion
- [ ] Integration with LinkedIn and other platforms

### Version History
- **v19.0** (Current): Enhanced human verification, smart caching
- **v18.x**: Improved error handling, dashboard features
- **v17.x**: Multi-source support, data validation
- **v16.x**: Initial production release

## 🙏 Acknowledgments

- **Selenium Team**: For the robust web automation framework
- **BeautifulSoup**: For excellent HTML parsing capabilities
- **Pandas**: For powerful data manipulation tools
- **Chart.js**: For interactive dashboard visualizations
- **Kenyan Job Boards**: For providing accessible job data

---

## 🏃‍♂️ Quick Commands

```bash
# Install and run
git clone https://github.com/your-repo/kenya-job-scraper.git
cd kenya-job-scraper
pip install -r requirements.txt
python kenya_job_scraper.py

# View dashboard
# Open jobs_dashboard_YYYY-MM-DD.html in your browser
```

---

**Made with ❤️ for the Kenyan job market**

*Last updated: July 28, 2025*
