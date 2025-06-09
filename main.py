import os
import time
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (NoSuchElementException, 
                                      TimeoutException, 
                                      WebDriverException)
import requests
from bs4 import BeautifulSoup
from configparser import ConfigParser

class OrderAutomationAgent:
    def __init__(self, config_file='config.ini'):
        # Initialize logger
        self.logger = self._setup_logger()
        
        # Load configuration
        self.config = self._load_config(config_file)
        
        # Initialize web driver
        self.driver = self._init_webdriver()
        
        # State variables
        self.current_order = None
        self.session_active = False

    def _setup_logger(self):
        """Configure logging system"""
        logger = logging.getLogger('OrderAutomationAgent')
        logger.setLevel(logging.INFO)
        
        # Create handlers
        console_handler = logging.StreamHandler()
        file_handler = logging.FileHandler('order_automation.log')
        
        # Create formatters and add to handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        return logger

    def _load_config(self, config_file):
        """Load configuration from INI file"""
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Configuration file {config_file} not found")
            
        config = ConfigParser()
        config.read(config_file)
        return config

    def _init_webdriver(self):
        """Initialize Selenium WebDriver with configured options"""
        chrome_options = Options()
        
        # Configure headless mode from config
        if self.config.getboolean('SELENIUM', 'HEADLESS', fallback=True):
            chrome_options.add_argument("--headless")
            
        # Add other options from config
        for option in self.config.get('SELENIUM', 'OPTIONS', fallback='').split(','):
            if option.strip():
                chrome_options.add_argument(option.strip())
                
        # Initialize driver
        try:
            driver = webdriver.Chrome(
                executable_path=self.config.get('SELENIUM', 'DRIVER_PATH', fallback='chromedriver'),
                options=chrome_options
            )
            driver.implicitly_wait(self.config.getint('SELENIUM', 'IMPLICIT_WAIT', fallback=10))
            return driver
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise

    def _safe_get(self, url, max_retries=3):
        """Safe URL navigation with retries"""
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                return True
            except WebDriverException as e:
                self.logger.warning(f"Attempt {attempt + 1} failed to load {url}: {str(e)}")
                if attempt == max_retries - 1:
                    self.logger.error(f"Failed to load {url} after {max_retries} attempts")
                    return False
                time.sleep(2 ** attempt)  # Exponential backoff

    def _extract_order_data(self):
        """Extract order data from Laravel/PHP portal"""
        portal_url = self.config.get('PORTAL', 'URL')
        portal_auth = {
            'username': self.config.get('PORTAL', 'USERNAME'),
            'password': self.config.get('PORTAL', 'PASSWORD')
        }
        
        try:
            # Login to portal
            self._safe_get(portal_url)
            
            # Fill login form (adjust selectors as needed)
            self.driver.find_element(By.NAME, 'username').send_keys(portal_auth['username'])
            self.driver.find_element(By.NAME, 'password').send_keys(portal_auth['password'])
            self.driver.find_element(By.XPATH, '//button[@type="submit"]').click()
            
            # Wait for dashboard to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'orders-table'))
            )
            
            # Extract order data (adjust selectors as needed)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            orders_table = soup.find('table', {'id': 'orders-table'})
            
            orders = []
            for row in orders_table.find_all('tr')[1:]:  # Skip header
                cells = row.find_all('td')
                order = {
                    'order_id': cells[0].text.strip(),
                    'product_name': cells[1].text.strip(),
                    'quantity': int(cells[2].text.strip()),
                    'customer_name': cells[3].text.strip(),
                    'shipping_address': cells[4].text.strip(),
                    'design_file': cells[5].find('a')['href'] if cells[5].find('a') else None,
                    'special_instructions': cells[6].text.strip()
                }
                orders.append(order)
                
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to extract order data: {str(e)}")
            return None

    def _place_order(self, order):
        """Place an individual order on the reseller website"""
        try:
            # Navigate to product page
            product_url = self._find_product_url(order['product_name'])
            if not product_url:
                self.logger.error(f"Product not found: {order['product_name']}")
                return False
                
            if not self._safe_get(product_url):
                return False
                
            # Select product options
            self._select_product_options(order)
            
            # Upload design file if available
            if order['design_file']:
                self._upload_design_file(order['design_file'])
                
            # Fill shipping information
            self._fill_shipping_info(order)
            
            # Submit order
            submit_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'submit-order'))
            )
            submit_button.click()
            
            # Verify order submission
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'order-confirmation'))
            )
            
            self.logger.info(f"Successfully placed order {order['order_id']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to place order {order['order_id']}: {str(e)}")
            return False

    def _find_product_url(self, product_name):
        """Find product URL by name (implementation depends on website structure)"""
        # This could be implemented by:
        # 1. Using site search functionality
        # 2. Accessing a predefined product URL mapping
        # 3. Crawling product categories
        
        # Example implementation using search:
        search_url = self.config.get('RESELLER', 'SEARCH_URL')
        self._safe_get(search_url)
        
        try:
            search_box = self.driver.find_element(By.ID, 'search-box')
            search_box.send_keys(product_name)
            search_box.submit()
            
            # Wait for results
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'product-item'))
            )
            
            # Get first result link
            first_result = self.driver.find_element(By.XPATH, '//div[@class="product-item"][1]/a')
            return first_result.get_attribute('href')
            
        except Exception:
            self.logger.warning(f"Product search failed for {product_name}")
            return None

    def _select_product_options(self, order):
        """Select product options and quantity"""
        try:
            # Set quantity
            qty_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, 'quantity'))
            )
            qty_input.clear()
            qty_input.send_keys(str(order['quantity']))
            
            # Handle other product options (color, size, etc.)
            if 'options' in order:
                for option_name, option_value in order['options'].items():
                    try:
                        # Try dropdown first
                        select = Select(self.driver.find_element(By.NAME, option_name))
                        select.select_by_visible_text(option_value)
                    except:
                        # Fallback to radio buttons or checkboxes
                        option_elem = self.driver.find_element(
                            By.XPATH, f'//input[@name="{option_name}" and @value="{option_value}"]')
                        option_elem.click()
                        
            # Handle custom instructions
            if order['special_instructions']:
                instructions = self.driver.find_element(By.ID, 'special-instructions')
                instructions.send_keys(order['special_instructions'])
                
        except Exception as e:
            self.logger.error(f"Failed to select product options: {str(e)}")
            raise

    def _upload_design_file(self, file_url):
        """Download and upload design file"""
        try:
            # Download the file
            local_path = os.path.join('downloads', os.path.basename(file_url))
            os.makedirs('downloads', exist_ok=True)
            
            response = requests.get(file_url, stream=True)
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Find upload element and send file path
            upload_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, 'design-file'))
            upload_element.send_keys(os.path.abspath(local_path))
            
        except Exception as e:
            self.logger.error(f"Failed to upload design file: {str(e)}")
            raise

    def _fill_shipping_info(self, order):
        """Fill shipping information form"""
        try:
            shipping_info = {
                'customer_name': order['customer_name'],
                'address': order['shipping_address'],
                # Add other fields from config or order data
            }
            
            for field, value in shipping_info.items():
                element = self.driver.find_element(By.NAME, field)
                element.clear()
                element.send_keys(value)
                
        except Exception as e:
            self.logger.error(f"Failed to fill shipping info: {str(e)}")
            raise

    def _handle_captcha(self):
        """Handle CAPTCHA challenges if they appear"""
        try:
            # Check if CAPTCHA exists
            captcha_element = self.driver.find_element(By.ID, 'captcha')
            self.logger.warning("CAPTCHA detected - requiring manual intervention")
            
            # Possible approaches:
            # 1. Pause and wait for manual solving
            # 2. Integrate with CAPTCHA solving service
            # 3. Use browser context with cookies
            
            # For now, just pause and notify
            input("Please solve the CAPTCHA and press Enter to continue...")
            return True
            
        except NoSuchElementException:
            return False  # No CAPTCHA found

    def process_orders(self):
        """Main method to process all pending orders"""
        self.logger.info("Starting order processing")
        
        try:
            # Extract orders from portal
            orders = self._extract_order_data()
            if not orders:
                self.logger.info("No orders to process")
                return
                
            # Process each order
            success_count = 0
            for order in orders:
                self.current_order = order
                self.logger.info(f"Processing order {order['order_id']}")
                
                if self._place_order(order):
                    success_count += 1
                    
                # Small delay between orders
                time.sleep(2)
                
            self.logger.info(f"Order processing complete. {success_count}/{len(orders)} orders successfully placed")
            return success_count
            
        except Exception as e:
            self.logger.error(f"Fatal error during order processing: {str(e)}")
            return 0
        finally:
            self.current_order = None

    def shutdown(self):
        """Clean up resources"""
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
        finally:
            self.driver = None
            self.session_active = False

# Example usage
if __name__ == "__main__":
    agent = OrderAutomationAgent()
    try:
        agent.process_orders()
    finally:
        agent.shutdown()