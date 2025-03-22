# MAE Brand Namer

MAE Brand Namer is an AI-powered brand name generation and analysis tool built with Streamlit and LangGraph. It helps businesses and entrepreneurs generate, evaluate, and analyze brand names through a sophisticated multi-agent system.

## Features

### 1. Brand Name Generation
- Interactive brand description input
- Industry classification with 3-level hierarchy
- Customizable parameters:
  - Target market
  - Geographic scope
  - Brand positioning
- Quick templates for common use cases

### 2. Comprehensive Analysis
- Linguistic analysis
- Semantic evaluation
- Cultural sensitivity check
- Domain availability
- SEO potential
- Market fit assessment
- Competitor analysis
- Translation viability

### 3. Advanced Visualization
- Interactive results display
- Radar charts for metrics
- Detailed analysis breakdowns
- Progress tracking
- Real-time execution flow

### 4. History & Management
- Session history tracking
- Favorites system
- Complete generation history
- Detailed run analysis
- LangSmith integration for debugging

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd mae_frontend
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file with the following:
```env
LANGGRAPH_STUDIO_URL=<your-langgraph-url>
LANGGRAPH_ASSISTANT_ID=<your-assistant-id>
LANGGRAPH_API_KEY=<your-api-key>
```

4. Run the application:
```bash
streamlit run streamlit_app.py
```

## Usage

1. **Enter Brand Requirements**
   - Provide a detailed description of your brand
   - Select industry classification (optional)
   - Specify target market and geographic scope
   - Choose brand positioning attributes

2. **Generate Names**
   - Click "Generate Brand Names" to start the process
   - Monitor real-time progress
   - View detailed analysis for each name

3. **Review Results**
   - Examine generated names
   - Review comprehensive analysis
   - Save favorites
   - Export detailed reports

4. **Access History**
   - View current session history
   - Access complete generation history
   - Load and review past generations
   - Track LangSmith traces for debugging

## Technical Details

### Dependencies
- streamlit
- requests
- pandas
- altair
- python-dotenv
- langchain

### API Integration
- LangGraph Studio API
- LangSmith for tracing and debugging
- Streamlit for the user interface

### Data Structure
- Three-tier industry classification
- Comprehensive brand analysis framework
- Persistent session state management
- Real-time streaming data processing

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Powered by LangGraph AI
- Built with Streamlit
- Integrated with LangSmith for advanced tracing and debugging 