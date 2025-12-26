import os
import time
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
SOURCE_URL = "https://www.canaraengineering.in/s-sports"
LOGIN_URL = "https://canaradashboard.vercel.app/login"
DASHBOARD_URL = "https://canaradashboard.vercel.app/dashboard/buzz"
USERNAME = "githubcec@canaraengineering.in"
PASSWORD = "123456"
DOWNLOAD_DIR = "webscraping"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def run():
    with sync_playwright() as p:
        # Launch browser (headless=False to verify visually)
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        context = browser.new_context()
        page = context.new_page()

        # --- PART 1: SCRAPE ALL EVENTS ---
        print(f"Navigating to {SOURCE_URL}...")
        try:
            page.goto(SOURCE_URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_selector("text=Read More", timeout=15000)
        except Exception as e:
            print(f"Navigation failed: {e}. Retrying...")
            page.goto(SOURCE_URL, timeout=60000, wait_until="domcontentloaded")

        # Find 'Read More' links
        read_more_elements = page.get_by_text("Read More")
        count = read_more_elements.count()
        print(f"Found {count} events.")

        if count == 0:
            print("No events found. Exiting.")
            return

        all_events = []

        # Iterate through all events in REVERSE order (Last -> First)
        # User request: "start 185, 184, 183 etc"
        for i in range(count - 1, -1, -1):
            print(f"\n--- Processing Event {i+1}/{count} (Reverse Order) ---")
            try:
                # We must re-query elements to avoid staleness if page refreshed
                
                # Click the i-th Read More link
                with context.expect_page(timeout=10000) as new_page_info:
                    read_more_elements.nth(i).click()
                detail_page = new_page_info.value
                detail_page.wait_for_load_state("domcontentloaded")
                print(f"Landed on details: {detail_page.url}")

                # Extract Data
                heading = detail_page.locator("h3").first.inner_text().strip()
                description = detail_page.locator("p").first.inner_text().strip()
                
                # Image scraping
                image_src = None
                try:
                    img_locator = detail_page.locator("center img").first
                    if img_locator.is_visible(timeout=2000):
                        image_src = img_locator.get_attribute("src")
                    else:
                        imgs = detail_page.locator("img").all()
                        for img in imgs:
                            src = img.get_attribute("src")
                            if src and ("upload" in src or "jpg" in src or "png" in src):
                                image_src = src
                                break
                except Exception as e:
                    print(f"Image scraping warning: {e}")
                
                if image_src and not image_src.startswith("http"):
                    image_src = "https://www.canaraengineering.in/" + image_src.lstrip("/")

                print(f"Scraped: {heading}")

                # Download Image
                local_image_path = None
                if image_src:
                    local_image_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, f"event_{i}.jpg"))
                    try:
                        response = detail_page.request.get(image_src, timeout=15000)
                        if response.status == 200:
                            with open(local_image_path, 'wb') as f:
                                f.write(response.body())
                            print("Image downloaded.")
                        else:
                            print(f"Values check: {response.status}")
                            # Fallback Screenshot
                            imgs = detail_page.locator("center img").first
                            if imgs.is_visible():
                                imgs.screenshot(path=local_image_path)
                                print("Fallback screenshot saved.")
                            else:
                                local_image_path = None
                    except Exception as e:
                        print(f"Image download failed: {e}")
                        local_image_path = None
                
                # Save to list
                all_events.append({
                    "title": heading,
                    "description": description,
                    "image_path": local_image_path
                })

                detail_page.close()
                # Bring main page to front just in case
                page.bring_to_front()
                
            except Exception as e:
                print(f"Error scraping event {i+1}: {e}")
                try:
                    detail_page.close()
                except:
                    pass

        print(f"\nScraping Complete. Collected {len(all_events)} events.")
        
        if not all_events:
            print("No events collected. Exiting.")
            return

        # --- PART 2: AUTOMATION LOGIN ---
        print("\nStarting Login for Automation...")
        if "dashboard" not in page.url:
            page.goto(LOGIN_URL)
            page.fill("input[type='email']", USERNAME)
            page.fill("input[type='password']", PASSWORD)
            page.click("button[type='submit']", timeout=5000)
            
            try:
                page.wait_for_url("**/dashboard", timeout=15000)
                print("Login successful.")
            except:
                print("Login check timed out. Proceeding...")

        # --- PART 3: UPLOAD LOOP ---
        for idx, event in enumerate(all_events):
            print(f"\n--- Uploading Event {idx+1}/{len(all_events)}: {event['title']} ---")
            
            try:
                print("Navigating to Buzz...")
                page.goto(DASHBOARD_URL)
                
                print("Opening 'Add Buzz' modal...")
                page.get_by_role("button", name="Add Buzz").click()
                
                # Wait for iframe
                iframe_element = page.wait_for_selector("iframe[src*='unlayer.com']", timeout=30000)
                frame = page.frame_locator("iframe[src*='unlayer.com']")
                
                # Wait for editors tools
                try:
                    frame.locator(".blockbuilder-tools-panel").wait_for(timeout=20000)
                except:
                    pass

                # Fill Title
                try:
                    page.locator("input[placeholder='Name of Event']").first.fill(event['title'])
                except:
                    page.locator("input[type='text']").first.fill(event['title'])

                # --- UNLAYER HELPER ---
                def drag_tool(tool_name):
                    try:
                        tool = frame.get_by_text(tool_name, exact=True).first
                        if not tool.is_visible():
                             tool = frame.locator(f"div:has-text('{tool_name}')").last
                        
                        target = frame.locator(".u_body").first
                        tool_box = tool.bounding_box()
                        target_box = target.bounding_box()

                        if not tool_box or not target_box:
                            return False

                        page.mouse.move(tool_box["x"] + tool_box["width"] / 2, tool_box["y"] + tool_box["height"] / 2)
                        page.mouse.down()
                        time.sleep(0.5)
                        page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=10)
                        time.sleep(0.5)
                        page.mouse.up()
                        page.mouse.up()
                        time.sleep(3)
                        return True
                    except:
                        return False

                # 1. TEXT (Replacing Heading)
                if drag_tool("Text"):
                    print("Text tool dropped.")
                    try:
                        # Find Text widget. usually .u_content_text
                        text_widget = frame.locator(".u_content_text").last
                        text_widget.click(force=True)
                        time.sleep(0.5)
                        
                        # Edit text
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(event['description'])
                        
                        # Close panel (if any)
                        try:
                            frame.get_by_label("Close").last.click()
                            time.sleep(1)
                        except:
                            frame.locator(".u_body").first.click()
                    except Exception as e:
                        print(f"Text edit failed: {e}")
                else:
                    print("Failed to drag Text tool.")

                # 2. IMAGE
                # Wait for tool list
                try:
                     frame.get_by_text("Image", exact=True).first.wait_for(timeout=5000)
                except:
                     frame.locator(".u_body").first.click()

                if event['image_path'] and drag_tool("Image"):
                    time.sleep(1)
                    try:
                        # Select block
                        last_block = frame.locator(".u_content_image, .u_image").last
                        if last_block.is_visible():
                            last_block.click(force=True)
                        else:
                            frame.locator(".u_content").last.click(force=True)
                        
                        time.sleep(1)
                        
                        # Upload
                        uploaded = False
                        
                        # Try text click
                        try:
                            drop_zone = frame.get_by_text("Drop a new image here", exact=False)
                            if drop_zone.count() > 0:
                                for k in range(drop_zone.count() - 1, -1, -1):
                                    if drop_zone.nth(k).is_visible():
                                        with page.expect_file_chooser(timeout=3000) as fc_info:
                                            drop_zone.nth(k).click(force=True, timeout=2000)
                                        fc_info.value.set_files(event['image_path'])
                                        uploaded = True
                                        break
                        except:
                            pass

                        if not uploaded:
                            # Hidden input
                            try:
                                frame.locator("input[type='file']").last.set_input_files(event['image_path'])
                                uploaded = True
                            except:
                                pass
                        
                        if uploaded:
                            print("Image uploaded.")
                            # Wait for render (text disappear)
                            try:
                                frame.locator("text=Drop a new image here").last.wait_for(state="hidden", timeout=10000)
                            except:
                                pass
                            time.sleep(5)
                            
                    except Exception as e:
                        print(f"Image logic failed: {e}")
                
                # SAVE
                print("Saving Buzz...")
                page.get_by_role("button", name="Save Buzz").click()
                time.sleep(3)
                print("Buzz Saved.")

            except Exception as e:
                print(f"Failed to upload event {idx+1}: {e}")

        print("\nAll operations complete.")
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    run()