from selenium import webdriver

options = webdriver.ChromeOptions()
# change the username
options.add_argument(r'user-data-dir=C:\Users\Vivek\AppData\Local\Google\Chrome\User Data')
options.add_argument('profile-directory=Default')         # change if u have diff profile name
driver = webdriver.Chrome(options=options)
