from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium import webdriver
import time

driver = webdriver.Chrome()
driver.maximize_window()

url = "https://www.google.com/"
driver.get(url)
time.sleep(2)

search_bar = driver.find_element(By.XPATH, '//*[@id="APjFqb"]')
search_bar.send_keys("machine learning")

# poll_frequency=0.5 : How often (in seconds) the condition is checked (default: 0.5 seconds)
# ignored_exceptions : A tuple of exceptions to ignore while waiting (optional)
wait = WebDriverWait(driver, 20, poll_frequency=0.5, ignored_exceptions=None) # wait for maximum of 5 seconds # wait till below condition is meet
wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/div[1]/div[3]/form/div[1]/div[1]/div[2]/div[4]/div[6]/center/input[1]')))

search_bar.send_keys(Keys.ENTER)

time.sleep(2)
driver.quit()
