'''MiniProject/ExpenseTrackerPython_v2.py
Telegram Expense Tracker Bot

This script is designed to track expenses using a Telegram bot and Google Sheets.
It allows users to add expenses, view reports, and manage their finances effectively.
Key features include:
Indian Rupees (₹) as Default Currency
Salary Tracking
Payment Method Tracking
Enhanced Reporting
Flexible Date Input
'''


import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler
)
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from gspread.exceptions import WorksheetNotFound
from dotenv import load_dotenv
import json

# --- Configuration ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Load environment variables from .env file
load_dotenv()

# --- Configuration (now loaded from environment) ---
SCOPE = ["https://spreadsheets.google.com/feeds", 
         "https://www.googleapis.com/auth/drive"]
 # Keep this file secure

GOOGLE_SHEETS_CREDENTIALS = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')


# Worksheet Names
EXPENSES_SHEET = 'Expenses'
SALARY_SHEET = 'Salary'
PAYMENT_METHODS = ['Cash', 'UPI', 'Card', 'Bank Transfer', 'Other']

# Initialize Google Sheets
credentials_info = json.loads(os.getenv("GOOGLE_SHEETS_CREDENTIALS"))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, SCOPE)
gc = gspread.authorize(credentials)

def get_or_create_worksheet(spreadsheet, title, headers):
    try:
        worksheet = spreadsheet.worksheet(title)
        print(f"Using existing worksheet: {title}")
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows="100", cols=str(len(headers)))
        worksheet.append_row(headers)
        print(f"Created new worksheet: {title}")
    return worksheet

# Initialize worksheets
spreadsheet = gc.open_by_key(SPREADSHEET_ID)
expenses_ws = get_or_create_worksheet(spreadsheet, EXPENSES_SHEET, 
                                    ["Date", "Category", "Amount (₹)", "Description", "Payment Method"])
salary_ws = get_or_create_worksheet(spreadsheet, SALARY_SHEET,
                                  ["Date", "Amount (₹)", "Description"])

# --- Helper Functions ---
def calculate_balance():
    """Calculate remaining balance after salary and expenses"""
    salary_data = salary_ws.get_all_records()
    salary_df = pd.DataFrame(salary_data)
    total_salary = salary_df['Amount (₹)'].sum() if not salary_df.empty else 0
    
    expense_data = expenses_ws.get_all_records()
    expense_df = pd.DataFrame(expense_data)
    total_expenses = expense_df['Amount (₹)'].sum() if not expense_df.empty else 0
    
    return total_salary - total_expenses

def get_current_month_expenses():
    """Get expenses for current month grouped by category"""
    expense_data = expenses_ws.get_all_records()
    if not expense_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(expense_data)
    df['Date'] = pd.to_datetime(df['Date'])
    current_month = pd.to_datetime('now').to_period('M')
    return df[df['Date'].dt.to_period('M') == current_month]

# --- Bot Commands ---
async def start(update: Update, context: CallbackContext):
    help_text = """
    💰 *Expense Tracker Bot* (₹) 💰
    
    _Add Expense:_
    - Basic: `food 250 lunch`
    - With date: `15/05 food 250 lunch`
    - With payment: `food 250 lunch via UPI`
    
    _Salary Commands:_
    /addsalary - Record your salary (₹)
    /balance - Show remaining balance
    
    _Other Commands:_
    /report - Monthly/Yearly reports
    /today - Today's expenses
    /payments - Payment method breakdown
    /help - Show this message
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: CallbackContext):
    """Handle expense entries"""
    message = update.message.text.lower()
    try:
        parts = message.split()
        
        # Parse payment method
        payment_method = "Cash"  # Default
        if 'via' in parts:
            via_index = parts.index('via')
            payment_method_raw = ' '.join(parts[via_index+1:]).strip()

            # Case-insensitive comparison
            for method in PAYMENT_METHODS:
                if payment_method_raw.lower() == method.lower():
                    payment_method = method
                break
            else:
                payment_method = "Other"
    
            parts = parts[:via_index]
        
        # Parse date (format: DD/MM or use today)
        if '/' in parts[0] and len(parts[0].split('/')) == 2:
            day, month = map(int, parts[0].split('/'))
            current_year = datetime.now().year
            try:
                expense_date = datetime(current_year, month, day).date()
            except ValueError:
                await update.message.reply_text("⚠️ Invalid date format. Use DD/MM")
                return
            parts = parts[1:]
        else:
            expense_date = datetime.now().date()
        
        # Parse category and amount (already in ₹)
        category = parts[0].title()
        try:
            amount = float(parts[1])
        except ValueError:
            await update.message.reply_text("⚠️ Invalid amount. Please enter numbers only")
            return
            
        description = ' '.join(parts[2:]) if len(parts) > 2 else ''

        # Add to Google Sheets
        expenses_ws.append_row([
            expense_date.strftime("%Y-%m-%d"),
            category,
            amount,
            description,
            payment_method
        ])

        # Calculate and show remaining balance
        balance = calculate_balance()
        response = (
            f"✅ Expense Added:\n"
            f"📅 Date: {expense_date.strftime('%d %b %Y')}\n"
            f"🏷 Category: {category}\n"
            f"💸 Amount: ₹{amount:.2f}\n"
            f"💳 Payment: {payment_method}\n"
            f"💰 Remaining Balance: ₹{balance:.2f}"
        )
        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Error: {str(e)}\n\n"
            "Use format: `category amount description via payment_method`\n"
            "Example: `food 250 lunch via UPI`",
            parse_mode='Markdown'
        )

async def add_salary(update: Update, context: CallbackContext):
    """Add salary entry"""
    try:
        if not context.args:
            await update.message.reply_text("Usage: /addsalary <amount> [description]")
            return
            
        amount = float(context.args[0])
        description = ' '.join(context.args[1:]) if len(context.args) > 1 else 'Monthly Salary'
        
        salary_ws.append_row([
            datetime.now().strftime("%Y-%m-%d"),
            amount,
            description
        ])
        
        balance = calculate_balance()
        await update.message.reply_text(
            f"💰 Salary Added: ₹{amount:.2f}\n"
            f"📝 {description}\n"
            f"💵 Current Balance: ₹{balance:.2f}"
        )
    except ValueError:
        await update.message.reply_text("⚠️ Invalid amount. Please enter numbers only")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def show_balance(update: Update, context: CallbackContext):
    """Show current balance and spending summary"""
    balance = calculate_balance()
    monthly_expenses = get_current_month_expenses()
    
    response = (
        f"💼 *Financial Summary*\n"
        f"💰 Current Balance: *₹{balance:.2f}*\n"
        f"📅 Month: {datetime.now().strftime('%B %Y')}\n\n"
    )
    
    if not monthly_expenses.empty:
        # Monthly spending by category
        by_category = monthly_expenses.groupby('Category')['Amount (₹)'].sum()
        response += "📊 *Monthly Expenses by Category:*\n"
        for category, amount in by_category.items():
            response += f"- {category}: ₹{amount:.2f}\n"
        
        # Monthly spending by payment method
        by_payment = monthly_expenses.groupby('Payment Method')['Amount (₹)'].sum()
        response += "\n💳 *Monthly Expenses by Payment Method:*\n"
        for method, amount in by_payment.items():
            response += f"- {method}: ₹{amount:.2f}\n"
    else:
        response += "No expenses recorded this month yet."
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def generate_report(update: Update, context: CallbackContext):
    """Generate monthly/yearly expense reports"""
    try:
        expense_data = expenses_ws.get_all_records()
        if not expense_data:
            await update.message.reply_text("No expenses recorded yet!")
            return
            
        df = pd.DataFrame(expense_data)
        df['Date'] = pd.to_datetime(df['Date'])
        df['Amount (₹)'] = pd.to_numeric(df['Amount (₹)'])
        
        # Current month and year analysis
        current_month = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year
        
        monthly_expenses = df[df['Date'].dt.to_period('M') == pd.to_datetime('now').to_period('M')]
        monthly_by_category = monthly_expenses.groupby('Category')['Amount (₹)'].sum()
        
        yearly_expenses = df[df['Date'].dt.year == current_year]
        yearly_by_category = yearly_expenses.groupby('Category')['Amount (₹)'].sum()

        # Plotting
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))
        
        # Monthly Pie Chart
        if not monthly_by_category.empty:
            ax1.pie(monthly_by_category, labels=monthly_by_category.index, autopct='%1.1f%%')
            ax1.set_title(f'Monthly Expenses ({current_month})')
        else:
            ax1.text(0.5, 0.5, 'No data\nfor current month', ha='center', va='center')
        
        # Yearly Pie Chart
        if not yearly_by_category.empty:
            ax2.pie(yearly_by_category, labels=yearly_by_category.index, autopct='%1.1f%%')
            ax2.set_title(f'Yearly Expenses ({current_year})')
        else:
            ax2.text(0.5, 0.5, 'No data\nfor current year', ha='center', va='center')

        plt.tight_layout()
        
        # Save and send the figure
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()

        # Send summary text with the chart
        monthly_total = monthly_by_category.sum() if not monthly_by_category.empty else 0
        yearly_total = yearly_by_category.sum() if not yearly_by_category.empty else 0
        summary = (
            f"📊 Expense Report (₹)\n\n"
            f"📅 {current_month} Total: ₹{monthly_total:.2f}\n"
            f"📅 {current_year} Total: ₹{yearly_total:.2f}"
        )
        
        await update.message.reply_photo(photo=buf, caption=summary)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error generating report: {str(e)}")

async def show_today_expenses(update: Update, context: CallbackContext):
    """Show expenses recorded today"""
    try:
        expense_data = expenses_ws.get_all_records()
        if not expense_data:
            await update.message.reply_text("No expenses recorded yet!")
            return
            
        df = pd.DataFrame(expense_data)
        today = datetime.now().date()
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        today_expenses = df[df['Date'] == today]
        
        if not today_expenses.empty:
            response = "📝 Today's Expenses (₹):\n\n"
            total = 0
            for _, row in today_expenses.iterrows():
                response += f"• {row['Category']}: ₹{row['Amount (₹)']:.2f}"
                if row['Description']:
                    response += f" ({row['Description']})"
                response += f" [{row['Payment Method']}]\n"
                total += row['Amount (₹)']
            response += f"\n💵 Today's Total: ₹{total:.2f}"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("No expenses recorded for today!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def payment_method_report(update: Update, context: CallbackContext):
    """Show payment method distribution"""
    try:
        expense_data = expenses_ws.get_all_records()
        if not expense_data:
            await update.message.reply_text("No expenses recorded yet!")
            return
            
        df = pd.DataFrame(expense_data)
        payment_dist = df.groupby('Payment Method')['Amount (₹)'].sum()
        
        # Plot
        plt.figure(figsize=(8, 8))
        plt.pie(payment_dist, labels=payment_dist.index, autopct='%1.1f%%')
        plt.title("Payment Method Distribution (₹)")
        
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        await update.message.reply_photo(
            photo=buf,
            caption="💳 Payment Method Distribution"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

def main():
    """Start the bot"""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CommandHandler("today", show_today_expenses))
    application.add_handler(CommandHandler("addsalary", add_salary))
    application.add_handler(CommandHandler("balance", show_balance))
    application.add_handler(CommandHandler("payments", payment_method_report))
    
    # Message Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
