// API Configuration
const API_CONFIG = {
   
    BASE_URL: window.location.hostname === 'localhost' 
        ? 'http://localhost:8000' 
        : 'https://production-domain.com/api'
    // BASE_URL: 'http://localhost:8000'
};


window.API_CONFIG = API_CONFIG;