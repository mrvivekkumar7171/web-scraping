import time
from selenium import webdriver

driver = webdriver.Chrome()
driver.maximize_window()

url = "https://www.google.com/search?sca_esv=e6cbb193bcbd8d96&q=jamshedpur-fc+image&udm=2&fbs=ABzOT_CWdhQLP1FcmU5B0fn3xuWpA-dk4wpBWOGsoR7DG5zJBnsX62dbVmWR6QCQ5QEtPRrN1KFHti9EP_dqC742rxzHRLBZCil0j9azScQIqAr91H0azpWlTOGvHqYN60vyJ2gFbBUHED7NsWoFuzDWThuQeiBSEA9WkBE5E0ozGVE-K7bQPqfajugGaNBRKoKDxshT_ivzyoOGCosbpgTVWWoF5NUC5Q&sa=X&ved=2ahUKEwie3fiAy4SMAxWaRmwGHdndAeUQtKgLegQIEBAB&biw=1366&bih=651&dpr=1"
driver.get(url)
time.sleep(2)

# calculate h1
prev_height = driver.execute_script("return document.body.scrollHeight")

while True:
	print(f"Webpage height: {prev_height:,} pixels")
	driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

	time.sleep(5)

    # calculate h2
	new_height = driver.execute_script("return document.body.scrollHeight")

	# NOTE: We can also replace the comparision with element comparision to scroll till one element is found
    # compare h1 and h2
	if prev_height == new_height:
		print('Reached the Page end !')
		break

	prev_height = new_height
