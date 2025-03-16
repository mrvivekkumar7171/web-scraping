import time
from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Chrome()
driver.maximize_window()

url = "https://en.wikipedia.org/wiki/Machine_learning"
driver.get(url)
time.sleep(2)

# "https://en.wikipedia.org/wiki/Machine_learning#Artificial_intelligenceis" the link for this section of wikipedia page so if are unable
# to find the id of the scroll then add manually Artificial_intelligenceis as id.
# scrolling to element (NOTE: It need to identify the element first)
ai_xpath = '//*[@id="Artificial_intelligence"]' 
ai_subtopic = driver.find_element(By.XPATH, ai_xpath)
driver.execute_script("arguments[0].scrollIntoView();", ai_subtopic)

# scrolling vertically (scroll by pixels)
driver.execute_script("window.scrollBy(0, 1000);") # scrolling down
time.sleep(3)
driver.execute_script("window.scrollBy(0, -500);") # scrolling up

# scrolling by page height (to go the bottom of the page)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(3)
driver.execute_script("window.scrollTo(0, -document.body.scrollHeight);")# to go back to top of the website
