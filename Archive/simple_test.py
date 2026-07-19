#!/usr/bin/env python3

import customtkinter as ctk
import sys
from datetime import datetime

def simple_test():
    """Simple test to ensure basic functionality"""
    root = ctk.CTk()
    root.title("Simple Test")
    root.geometry("800x600")
    root.configure(fg_color='#0D1117')
    
    main_frame = ctk.CTkFrame(root, fg_color='#161B22', corner_radius=20)
    main_frame.pack(fill='both', expand=True, padx=30, pady=30)
    
    # Test label
    test_label = ctk.CTkLabel(
        main_frame, 
        text="Test Application Running",
        font=ctk.CTkFont(size=24, weight="bold"),
        text_color='#C9D1D9'
    )
    test_label.pack(pady=50)
    
    # Test button
    close_btn = ctk.CTkButton(
        main_frame,
        text="Close",
        command=root.destroy,
        width=120,
        height=40
    )
    close_btn.pack(pady=20)
    
    print("Simple test app started successfully")
    
    root.mainloop()

if __name__ == "__main__":
    simple_test()