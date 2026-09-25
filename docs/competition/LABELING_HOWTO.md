# Label review in CVAT: 10-line how-to (owner)

1. Open http://127.0.0.1:8081 and log in with the account from `cvat/.env.cvat`. Open the task **trayagent-v1**, then **Job #1**.
2. Every image already has green boxes from the pre-labeler. Your job is to *fix* them, not to draw from scratch.
3. One box per jewelry item (ring, pendant, earring, bracelet, necklace). The label is always `item`. No box for empty slots, price tags, the tray, or reflections.
4. Wrong box: click it, then **Delete**. Missing item: press **N**, drag a tight rectangle around the whole item, press **N** again.
5. The box should touch the item's outer edge (including a chain loop), not the velvet slot around it.
6. Earring pairs: one box per earring. A necklace on a stand: one box.
7. An item hidden under glare but visible in real life: box where it is, if you can see any part of it. Otherwise leave it out and write the image number in `datasets/vj_items/review_notes.txt` with "glare-hidden".
8. Press **F** for the next image and **D** for the previous one. Press **Ctrl+S** often.
9. When every image is done, **Menu → Finish the job**. Then tell the engineer the task id (in the URL).
10. Aim for about 30 s per image. If you are unsure about an image, write its number in `review_notes.txt` with "unsure" and move on; we review those together.
