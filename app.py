from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import json
import os
from datetime import datetime
import requests

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# In-memory storage (will reset on restart - good for POC)
STATEMENTS = {}
TRANSACTIONS = {}
LEDGERS = [
    {"id": 1, "name": "HDFC Bank", "type": "Bank Accounts"},
    {"id": 2, "name": "Suspense Account", "type": "Current Liabilities"},
    {"id": 3, "name": "Bank Charges", "type": "Indirect Expenses"},
]
CONNECTOR_CONFIG = {
    "url": "",
    "token": ""
}

DEFAULT_LEDGER_ID = 2  # Suspense Account

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html', 
                         connector_configured=bool(CONNECTOR_CONFIG['url']))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Configure connector URL and token"""
    if request.method == 'POST':
        CONNECTOR_CONFIG['url'] = request.form.get('connector_url', '').strip()
        CONNECTOR_CONFIG['token'] = request.form.get('auth_token', '').strip()
        
        if CONNECTOR_CONFIG['url'] and CONNECTOR_CONFIG['token']:
            flash('Connector settings saved successfully!', 'success')
            
            # Test connection
            try:
                response = requests.get(
                    f"{CONNECTOR_CONFIG['url']}/api/status",
                    timeout=5
                )
                if response.status_code == 200:
                    flash('✅ Connector is online and reachable!', 'success')
                else:
                    flash('⚠️ Connector responded but with an error', 'warning')
            except:
                flash('⚠️ Could not reach connector. Make sure it is running.', 'warning')
            
            return redirect(url_for('index'))
        else:
            flash('Please fill in both fields', 'error')
    
    return render_template('settings.html', config=CONNECTOR_CONFIG)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Upload bank statement JSON"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('upload'))
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('upload'))
        
        if file and file.filename.endswith('.json'):
            try:
                # Read and parse JSON
                json_data = json.load(file)
                
                # Generate statement ID
                statement_id = f"stmt_{len(STATEMENTS) + 1}"
                
                # Store statement
                STATEMENTS[statement_id] = {
                    'data': json_data,
                    'uploaded_at': datetime.now().isoformat()
                }
                
                # Extract transactions
                page_data = json_data.get('page_1', {})
                transactions = page_data.get('transactions', [])
                
                # Store transactions with default ledger
                trans_list = []
                for idx, txn in enumerate(transactions):
                    trans_id = f"{statement_id}_txn_{idx}"
                    TRANSACTIONS[trans_id] = {
                        'statement_id': statement_id,
                        'index': idx,
                        'data': txn,
                        'ledger_id': DEFAULT_LEDGER_ID  # Auto-assign to Suspense
                    }
                    trans_list.append(trans_id)
                
                STATEMENTS[statement_id]['transaction_ids'] = trans_list
                
                flash(f'✅ Uploaded successfully! {len(transactions)} transactions found.', 'success')
                return redirect(url_for('transactions', statement_id=statement_id))
                
            except json.JSONDecodeError:
                flash('Invalid JSON file', 'error')
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'error')
        else:
            flash('Please upload a JSON file', 'error')
    
    return render_template('upload_xml.html', statements=STATEMENTS)

@app.route('/transactions/<statement_id>')
def transactions(statement_id):
    """View and manage transactions"""
    if statement_id not in STATEMENTS:
        flash('Statement not found', 'error')
        return redirect(url_for('upload'))
    
    statement = STATEMENTS[statement_id]
    page_data = statement['data'].get('page_1', {})
    summary = page_data.get('summary', {})
    
    # Get transactions with assigned ledgers
    trans_data = []
    for trans_id in statement.get('transaction_ids', []):
        if trans_id in TRANSACTIONS:
            trans = TRANSACTIONS[trans_id]
            ledger = next((l for l in LEDGERS if l['id'] == trans['ledger_id']), None)
            trans_data.append({
                'id': trans_id,
                'data': trans['data'],
                'ledger': ledger
            })
    
    return render_template('transactions.html',
                         statement_id=statement_id,
                         summary=summary,
                         transactions=trans_data,
                         ledgers=LEDGERS)

@app.route('/update-ledger', methods=['POST'])
def update_ledger():
    """Update ledger assignment for a transaction"""
    data = request.json
    trans_id = data.get('transaction_id')
    ledger_id = int(data.get('ledger_id'))
    
    if trans_id in TRANSACTIONS:
        TRANSACTIONS[trans_id]['ledger_id'] = ledger_id
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Transaction not found'}), 404

@app.route('/generate-xml/<statement_id>')
def generate_xml(statement_id):
    """Generate and preview XML"""
    if statement_id not in STATEMENTS:
        flash('Statement not found', 'error')
        return redirect(url_for('upload'))
    
    statement = STATEMENTS[statement_id]
    
    # Generate XML from transactions
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<ENVELOPE>')
    xml_parts.append('  <HEADER>')
    xml_parts.append('    <TALLYREQUEST>Import Data</TALLYREQUEST>')
    xml_parts.append('  </HEADER>')
    xml_parts.append('  <BODY>')
    xml_parts.append('    <IMPORTDATA>')
    xml_parts.append('      <REQUESTDESC>')
    xml_parts.append('        <REPORTNAME>Vouchers</REPORTNAME>')
    xml_parts.append('      </REQUESTDESC>')
    xml_parts.append('      <REQUESTDATA>')
    xml_parts.append('        <TALLYMESSAGE xmlns:UDF="TallyUDF">')
    
    # Process each transaction
    for trans_id in statement.get('transaction_ids', []):
        if trans_id not in TRANSACTIONS:
            continue
        
        trans = TRANSACTIONS[trans_id]
        txn_data = trans['data']
        ledger = next((l for l in LEDGERS if l['id'] == trans['ledger_id']), None)
        
        if not ledger:
            continue
        
        # Determine if debit or credit
        debit = txn_data.get('Debit', '').strip()
        credit = txn_data.get('Credit', '').strip()
        
        if not debit and not credit:
            continue
        
        is_debit = bool(debit)
        voucher_type = 'Payment' if is_debit else 'Receipt'
        amount = debit if is_debit else credit
        amount = amount.replace(',', '')
        
        # Parse date
        date_str = txn_data.get('Trans Date and Time', '').split()[0] if txn_data.get('Trans Date and Time') else ''
        if date_str:
            try:
                parts = date_str.split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    if len(year) == 2:
                        year = '20' + year
                    tally_date = f"{year}{month.zfill(2)}{day.zfill(2)}"
                else:
                    tally_date = datetime.now().strftime('%Y%m%d')
            except:
                tally_date = datetime.now().strftime('%Y%m%d')
        else:
            tally_date = datetime.now().strftime('%Y%m%d')
        
        xml_parts.append(f'          <VOUCHER VCHTYPE="{voucher_type}" ACTION="Create">')
        xml_parts.append(f'            <DATE>{tally_date}</DATE>')
        xml_parts.append(f'            <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>')
        xml_parts.append(f'            <NARRATION>{txn_data.get("Transaction Details", "")}</NARRATION>')
        
        if txn_data.get('Cheque No'):
            xml_parts.append(f'            <REFERENCE>{txn_data.get("Cheque No")}</REFERENCE>')
        
        # Bank ledger entry
        xml_parts.append('            <ALLLEDGERENTRIES.LIST>')
        xml_parts.append('              <LEDGERNAME>HDFC Bank</LEDGERNAME>')
        xml_parts.append(f'              <ISDEEMEDPOSITIVE>{"Yes" if is_debit else "No"}</ISDEEMEDPOSITIVE>')
        xml_parts.append(f'              <AMOUNT>{"-" if is_debit else ""}{amount}</AMOUNT>')
        xml_parts.append('            </ALLLEDGERENTRIES.LIST>')
        
        # Assigned ledger entry
        xml_parts.append('            <ALLLEDGERENTRIES.LIST>')
        xml_parts.append(f'              <LEDGERNAME>{ledger["name"]}</LEDGERNAME>')
        xml_parts.append(f'              <ISDEEMEDPOSITIVE>{"No" if is_debit else "Yes"}</ISDEEMEDPOSITIVE>')
        xml_parts.append(f'              <AMOUNT>{"-" if not is_debit else ""}{amount}</AMOUNT>')
        xml_parts.append('            </ALLLEDGERENTRIES.LIST>')
        
        xml_parts.append('          </VOUCHER>')
    
    xml_parts.append('        </TALLYMESSAGE>')
    xml_parts.append('      </REQUESTDATA>')
    xml_parts.append('    </IMPORTDATA>')
    xml_parts.append('  </BODY>')
    xml_parts.append('</ENVELOPE>')
    
    xml_data = '\n'.join(xml_parts)
    
    # Store XML in statement
    STATEMENTS[statement_id]['xml'] = xml_data
    
    return render_template('preview_xml.html',
                         statement_id=statement_id,
                         xml_data=xml_data,
                         connector_configured=bool(CONNECTOR_CONFIG['url']))

@app.route('/send-to-connector/<statement_id>', methods=['POST'])
def send_to_connector(statement_id):
    """Send XML to connector"""
    if statement_id not in STATEMENTS:
        return jsonify({'success': False, 'message': 'Statement not found'}), 404
    
    if not CONNECTOR_CONFIG['url'] or not CONNECTOR_CONFIG['token']:
        return jsonify({'success': False, 'message': 'Connector not configured'}), 400
    
    statement = STATEMENTS[statement_id]
    xml_data = statement.get('xml')
    
    if not xml_data:
        return jsonify({'success': False, 'message': 'XML not generated'}), 400
    
    try:
        # Send to connector
        response = requests.post(
            f"{CONNECTOR_CONFIG['url']}/api/receive-xml",
            headers={
                'Authorization': f"Bearer {CONNECTOR_CONFIG['token']}",
                'Content-Type': 'application/json'
            },
            json={'xml': xml_data},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            return jsonify({
                'success': True,
                'message': 'XML sent to connector successfully!',
                'timestamp': result.get('timestamp')
            })
        elif response.status_code == 401:
            return jsonify({
                'success': False,
                'message': 'Authentication failed. Check your token.'
            }), 401
        else:
            return jsonify({
                'success': False,
                'message': f'Connector returned error: {response.status_code}'
            }), response.status_code
            
    except requests.exceptions.ConnectionError:
        return jsonify({
            'success': False,
            'message': 'Could not connect to connector. Is it running?'
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': 'Connection timeout. Connector may be slow or offline.'
        }), 504
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/upload-xml', methods=['GET', 'POST'])
def upload_xml():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(url_for('upload_xml'))

        file = request.files['file']

        if file.filename == '' or not file.filename.endswith('.xml'):
            flash('Please upload a valid XML file', 'error')
            return redirect(url_for('upload_xml'))

        xml_data = file.read().decode('utf-8')

        # Store temporarily in session (POC safe)
        session['xml_data'] = xml_data

        flash('✅ XML uploaded successfully', 'success')
        return redirect(url_for('preview_xml'))

    return render_template('upload_xml.html')

@app.route('/preview-xml')
def preview_xml():
    xml_data = session.get('xml_data')

    if not xml_data:
        flash('No XML uploaded', 'error')
        return redirect(url_for('upload_xml'))

    return render_template(
        'preview_xml.html',
        xml_data=xml_data,
        connector_configured=bool(CONNECTOR_CONFIG['url'])
    )

@app.route('/sync-with-tally', methods=['POST'])
def sync_with_tally():
    if not CONNECTOR_CONFIG['url'] or not CONNECTOR_CONFIG['token']:
        return jsonify({'success': False, 'message': 'Connector not configured'}), 400

    xml_data = session.get('xml_data')
    if not xml_data:
        return jsonify({'success': False, 'message': 'No XML uploaded'}), 400

    try:
        response = requests.post(
            f"{CONNECTOR_CONFIG['url']}/api/receive-xml",
            headers={
                'Authorization': f"Bearer {CONNECTOR_CONFIG['token']}",
                'Content-Type': 'application/json'
            },
            json={'xml': xml_data},
            timeout=10
        )

        return jsonify({
            'success': True,
            'tally_response': response.text
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
