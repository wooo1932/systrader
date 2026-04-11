"""
PoC: Verify CpSvr8092S news events fire in Python.
Run with 32-bit Python while CYBOS Plus is connected.

Usage: python poc/test_news_event.py
"""
import sys
import time
import pythoncom
import win32com.client
import win32event


class NewsHandler:
    received_count = 0

    def OnReceived(self):
        NewsHandler.received_count += 1
        code = self._obj.GetHeaderValue(1)
        title = self._obj.GetHeaderValue(5)
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] #{NewsHandler.received_count} code={code} title={title}")


def check_connection():
    cybos = win32com.client.Dispatch("CpUtil.CpCybos")
    if cybos.IsConnect == 0:
        print("ERROR: CYBOS Plus is not connected.")
        print("Launch CYBOS Plus and log in first.")
        sys.exit(1)
    server_type = cybos.GetStockMarketKind("A005930")
    print(f"CYBOS connected. Server type check: {server_type}")


def main():
    pythoncom.CoInitialize()
    check_connection()

    print("Subscribing to CpSvr8092S news events...")
    try:
        news = win32com.client.DispatchWithEvents("Dscbo1.CpSvr8092S", NewsHandler)
        news.Subscribe()
        print("Subscribed. Waiting for news events (Ctrl+C to stop)...")
    except Exception as e:
        print(f"DispatchWithEvents failed: {e}")
        print("Trying WithEvents pattern instead...")
        news_obj = win32com.client.Dispatch("Dscbo1.CpSvr8092S")
        handler = win32com.client.WithEvents(news_obj, NewsHandler)
        news_obj.Subscribe()
        print("WithEvents subscribed. Waiting for news events (Ctrl+C to stop)...")

    stop_event = win32event.CreateEvent(None, 0, 0, None)
    try:
        while True:
            rc = win32event.MsgWaitForMultipleObjects(
                [stop_event], 0, 1000, win32event.QS_ALLEVENTS
            )
            if rc == win32event.WAIT_OBJECT_0 + 1:
                pythoncom.PumpWaitingMessages()
            # Print heartbeat every 30 seconds
            if NewsHandler.received_count == 0 and int(time.time()) % 30 == 0:
                print(f"  ... still waiting (no events yet)")
    except KeyboardInterrupt:
        print(f"\nStopped. Total events received: {NewsHandler.received_count}")
        if NewsHandler.received_count == 0:
            print("No events received. Possible causes:")
            print("  1. No news published during test period")
            print("  2. CpSvr8092S events may not work in Python")
            print("  3. Try running during market hours")
        news.Unsubscribe()


if __name__ == "__main__":
    main()
