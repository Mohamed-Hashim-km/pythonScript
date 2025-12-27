import os
import time
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
        # Launch browser
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        context = browser.new_context()
        page = context.new_page()

        # ==========================================
        # PART 1: ROBUST SCRAPING
        # ==========================================
        print(f"Navigating to {SOURCE_URL}...")
        try:
            page.goto(SOURCE_URL, timeout=60000, wait_until="domcontentloaded")
            # Wait for the main list to actually appear
            page.wait_for_selector("text=Read More", timeout=15000)
        except Exception as e:
            print(f"Initial navigation warning: {e}. Retrying...")
            page.goto(SOURCE_URL, timeout=60000, wait_until="domcontentloaded")

        # Find 'Read More' links
        read_more_elements = page.get_by_text("Read More")
        count = read_more_elements.count()
        print(f"Found {count} events.")

        if count == 0:
            print("No events found. Exiting.")
            return

        all_events = []

        # Iterate through all events in REVERSE order
        for i in range(count - 1, -1, -1):
            print(f"\n--- Processing Event {i+1}/{count} (Reverse Order) ---")
            
            detail_page = None
            try:
                # 1. Click "Read More" and handle the new tab
                # We re-query the button inside the loop to avoid "stale element" errors
                current_button = page.get_by_text("Read More").nth(i)
                
                with context.expect_page(timeout=20000) as new_page_info:
                    current_button.click()
                
                detail_page = new_page_info.value
                
                # --- FIX: WAIT FOR DATA TO LOAD ---
                print("Waiting for data to load...")
                
                # A. Wait for network connections to finish (fixes empty data from APIs)
                try:
                    detail_page.wait_for_load_state("networkidle", timeout=6000)
                except:
                    pass # Proceed even if network is busy, the selector wait is the real check
                
                # B. Wait explicitly for the Title (H3) to be VISIBLE
                # This ensures we don't scrape while the page is still white/loading
                detail_page.wait_for_selector("h3", state="visible", timeout=10000)
                
                # C. Extract Data
                heading = detail_page.locator("h3").first.inner_text().strip()
                
                # Get description (Wait for paragraph)
                description = ""
                if detail_page.locator("p").first.is_visible():
                    description = detail_page.locator("p").first.inner_text().strip()
                
                print(f"Scraped Title: {heading}")

                # D. Robust Image Scraping
                image_src = None
                try:
                    # Wait for image to appear
                    detail_page.wait_for_selector("img", timeout=5000)
                    
                    # Strategy 1: Look for image in <center> tag (common on this site)
                    if detail_page.locator("center img").first.is_visible():
                        image_src = detail_page.locator("center img").first.get_attribute("src")
                    
                    # Strategy 2: Look for any image with 'upload' or extension in URL
                    if not image_src:
                        imgs = detail_page.locator("img").all()
                        for img in imgs:
                            src = img.get_attribute("src")
                            if src and any(ext in src.lower() for ext in [".jpg", ".png", ".jpeg", "upload"]):
                                # Filter out logos/icons
                                if "logo" not in src.lower():
                                    image_src = src
                                    break
                except Exception as e:
                    print(f"Image finding warning: {e}")

                # E. Fix Relative URLs
                if image_src and not image_src.startswith("http"):
                    image_src = "https://www.canaraengineering.in/" + image_src.lstrip("/")

                # F. Download Image
                local_image_path = None
                if image_src:
                    local_image_path = os.path.abspath(os.path.join(DOWNLOAD_DIR, f"event_{i}.jpg"))
                    try:
                        # Use Playwright's request context to download
                        response = detail_page.request.get(image_src, timeout=10000)
                        if response.status == 200:
                            with open(local_image_path, 'wb') as f:
                                f.write(response.body())
                            print("Image downloaded successfully.")
                        else:
                            print(f"Image download failed (Status {response.status}). Trying screenshot...")
                            # Fallback: Screenshot the image element
                            img_el = detail_page.locator("center img").first
                            if img_el.is_visible():
                                img_el.screenshot(path=local_image_path)
                    except Exception as e:
                        print(f"Image download error: {e}")
                        local_image_path = None
                
                # Save to list
                all_events.append({
                    "title": heading,
                    "description": description,
                    "image_path": local_image_path
                })

                detail_page.close()
                page.bring_to_front()
                
            except Exception as e:
                print(f"Error scraping event {i+1}: {e}")
                if detail_page:
                    try: detail_page.close()
                    except: pass
                page.bring_to_front()

        print(f"\nScraping Complete. Collected {len(all_events)} events.")
        
        if not all_events:
            print("No events collected. Exiting.")
            return

        # ==========================================
        # PART 2: AUTOMATION LOGIN
        # ==========================================
        print("\nStarting Login for Automation...")
        if "dashboard" not in page.url:
            page.goto(LOGIN_URL)
            page.fill("input[type='email']", USERNAME)
            page.fill("input[type='password']", PASSWORD)
            page.click("button[type='submit']")
            
            try:
                page.wait_for_url("**/dashboard", timeout=15000)
                print("Login successful.")
            except:
                print("Login check timed out (might still be logged in). Proceeding...")

        # ==========================================
        # PART 3: UPLOAD LOOP
        # ==========================================
        for idx, event in enumerate(all_events):
            print(f"\n--- Uploading Event {idx+1}/{len(all_events)}: {event['title']} ---")
            
            try:
                page.goto(DASHBOARD_URL)
                
                # Click Add Buzz
                page.wait_for_selector("button:has-text('Add Buzz')", timeout=10000)
                page.get_by_role("button", name="Add Buzz").click()
                
                # Wait for Unlayer Iframe
                iframe_element = page.wait_for_selector("iframe[src*='unlayer.com']", timeout=30000)
                frame = page.frame_locator("iframe[src*='unlayer.com']")
                
                # Wait for tools to be ready
                try:
                    frame.locator(".blockbuilder-tools-panel").wait_for(timeout=20000)
                except:
                    pass

                # Fill Title (Outside iframe)
                try:
                    page.locator("input[placeholder='Name of Event']").first.fill(event['title'])
                except:
                    page.locator("input[type='text']").first.fill(event['title'])

                # --- Helper: Drag & Drop Tool ---
                def drag_tool(tool_name):
                    try:
                        # Find the tool icon on the right
                        tool = frame.get_by_text(tool_name, exact=True).first
                        if not tool.is_visible():
                             tool = frame.locator(f"div:has-text('{tool_name}')").last
                        
                        # Find the drop target (the canvas body)
                        target = frame.locator(".u_body").first
                        
                        tool_box = tool.bounding_box()
                        target_box = target.bounding_box()

                        if not tool_box or not target_box:
                            return False

                        # Perform Drag
                        page.mouse.move(tool_box["x"] + tool_box["width"] / 2, tool_box["y"] + tool_box["height"] / 2)
                        page.mouse.down()
                        time.sleep(0.5)
                        page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=10)
                        time.sleep(0.5)
                        page.mouse.up()
                        time.sleep(2) # Wait for tool to render on canvas
                        return True
                    except:
                        return False

                # 1. TEXT (Description)
                if drag_tool("Text"):
                    try:
                        text_widget = frame.locator(".u_content_text").last
                        text_widget.click(force=True)
                        time.sleep(0.5)
                        
                        # Clear and Type
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(event['description'])
                        
                        # Close editing panel
                        frame.locator(".u_body").first.click()
                    except Exception as e:
                        print(f"Text edit failed: {e}")

                # 2. IMAGE
                if event['image_path'] and drag_tool("Image"):
                    try:
                        # Click the image block on the canvas to open settings
                        last_block = frame.locator(".u_content_image, .u_image").last
                        last_block.click(force=True)
                        time.sleep(1)
                        
                        # Look for upload button/area
                        uploaded = False
                        
                        # Try finding file input directly
                        file_input = frame.locator("input[type='file']").last
                        if file_input.count() > 0:
                            file_input.set_input_files(event['image_path'])
                            uploaded = True
                        
                        # If that failed, try clicking "Upload Image" button
                        if not uploaded:
                            upload_btn = frame.get_by_text("Upload Image", exact=False).first
                            if upload_btn.is_visible():
                                with page.expect_file_chooser() as fc_info:
                                    upload_btn.click()
                                fc_info.value.set_files(event['image_path'])
                                uploaded = True

                        if uploaded:
                            print("Image uploaded.")
                            # Wait for upload processing (text overlay usually disappears)
                            time.sleep(5)
                            
                    except Exception as e:
                        print(f"Image upload logic failed: {e}")
                
                # SAVE
                print("Saving Buzz...")
                # Exit iframe context to click main page save button
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