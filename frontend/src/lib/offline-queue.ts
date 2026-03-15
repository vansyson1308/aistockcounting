const DB_NAME = 'vjsc-offline';
const STORE_NAME = 'pending-saves';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE_NAME, { autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function enqueue(url: string, body: string): Promise<void> {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  tx.objectStore(STORE_NAME).add({ url, body, timestamp: Date.now() });
  await new Promise((resolve, reject) => {
    tx.oncomplete = resolve;
    tx.onerror = reject;
  });
  db.close();
}

export async function flush(): Promise<number> {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const store = tx.objectStore(STORE_NAME);
  const items: { key: IDBValidKey; value: { url: string; body: string } }[] = [];

  await new Promise<void>((resolve, reject) => {
    const cursor = store.openCursor();
    cursor.onsuccess = () => {
      const c = cursor.result;
      if (c) {
        items.push({ key: c.key, value: c.value });
        c.continue();
      } else {
        resolve();
      }
    };
    cursor.onerror = reject;
  });

  let synced = 0;
  for (const { key, value } of items) {
    try {
      const res = await fetch(value.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: value.body,
      });
      if (res.ok) {
        store.delete(key);
        synced++;
      }
    } catch {
      // Still offline, stop trying
      break;
    }
  }

  db.close();
  return synced;
}

export async function getPendingCount(): Promise<number> {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, 'readonly');
  const count = await new Promise<number>((resolve, reject) => {
    const req = tx.objectStore(STORE_NAME).count();
    req.onsuccess = () => resolve(req.result);
    req.onerror = reject;
  });
  db.close();
  return count;
}
