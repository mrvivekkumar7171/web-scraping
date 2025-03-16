# In POM, Class represents to Page, Elements represents to Attributes, Methods represents to Interations.
import time
from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Chrome()
driver.maximize_window()

url = "https://github.com/login"
driver.get(url)
time.sleep(2)

# Page
class LoginPage:
	# Attributes
	def __init__(self, driver):
		self.driver = driver
		self.username = (By.ID, "login_field") # username field using ID
		self.password = (By.ID, "password")# password field using ID
		self.login_button = (By.NAME, "commit")# submit button

# Many a time Submit button is constructed in HTML without using <form> tag, so instead of using submit button find the element and click

	# Interations
	def login(self, username, password):
		self.driver.find_element(*self.username).send_keys(username)
		self.driver.find_element(*self.password).send_keys(password)
		time.sleep(1)
		self.driver.find_element(*self.login_button).click()

login_page = LoginPage(driver)
login_page.login("mrvivekkumar7171", "forgot-my-password")

time.sleep(2)
driver.quit()