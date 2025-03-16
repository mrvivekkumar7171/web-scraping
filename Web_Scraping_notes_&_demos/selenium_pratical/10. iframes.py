import time
from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Chrome()
driver.maximize_window()

url = "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_iframe_target"
driver.get(url)
time.sleep(2)

# identify iframe element main html and copy the path of iframe and switch to iframe's HTML document.
iframe_element = driver.find_element(By.XPATH, '//*[@id="iframeResult"]')
driver.switch_to.frame(iframe_element)

# Once the iframe is activated, we can work on the iframe's HTML document, until switch back to default.
link = driver.find_element(By.XPATH, '/html/body/p[1]/a')
link.click()
time.sleep(2)

# switch back to default main HTML
driver.switch_to.default_content()

driver.quit()