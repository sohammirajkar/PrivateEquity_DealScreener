#!/usr/bin/env python3
"""
Backend API Testing Suite for Deal Screener + LBO Application
Tests all backend endpoints as specified in the review request.
"""

import requests
import json
import uuid
import io
from typing import Dict, Any, List
import time

# Base URL from environment configuration
BASE_URL = "https://dealflow-metrics-1.preview.emergentagent.com/api"

class BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = []
        self.created_deal_id = None
        
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   Details: {details}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        
    def test_health_endpoint(self):
        """Test 1: Health check GET /api/"""
        try:
            response = self.session.get(f"{BASE_URL}/")
            if response.status_code == 200:
                data = response.json()
                if "message" in data:
                    self.log_test("Health Check", True, f"Response: {data}")
                    return True
                else:
                    self.log_test("Health Check", False, f"Missing 'message' in response: {data}")
                    return False
            else:
                self.log_test("Health Check", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Health Check", False, f"Exception: {str(e)}")
            return False
            
    def test_seed_endpoint(self):
        """Test 2: Seed data POST /api/seed expect {inserted:3}"""
        try:
            response = self.session.post(f"{BASE_URL}/seed")
            if response.status_code == 200:
                data = response.json()
                if "inserted" in data and data["inserted"] == 3:
                    self.log_test("Seed Data", True, f"Inserted {data['inserted']} records")
                    return True
                else:
                    self.log_test("Seed Data", False, f"Expected inserted:3, got: {data}")
                    return False
            else:
                self.log_test("Seed Data", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Seed Data", False, f"Exception: {str(e)}")
            return False
            
    def test_list_deals(self):
        """Test 3: List deals GET /api/deals - check UUID ids, ev_ebitda, score present"""
        try:
            response = self.session.get(f"{BASE_URL}/deals")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    # Check first deal for required fields
                    deal = data[0]
                    issues = []
                    
                    # Check if id is UUID string
                    if "id" not in deal:
                        issues.append("Missing 'id' field")
                    else:
                        try:
                            uuid.UUID(deal["id"])
                        except ValueError:
                            issues.append(f"ID is not a valid UUID: {deal['id']}")
                    
                    # Check ev_ebitda present
                    if "ev_ebitda" not in deal:
                        issues.append("Missing 'ev_ebitda' field")
                    elif deal["ev_ebitda"] is None:
                        issues.append("ev_ebitda is null")
                        
                    # Check score present
                    if "score" not in deal:
                        issues.append("Missing 'score' field")
                    elif deal["score"] is None:
                        issues.append("score is null")
                        
                    if not issues:
                        self.log_test("List Deals", True, f"Found {len(data)} deals with proper structure")
                        return True
                    else:
                        self.log_test("List Deals", False, f"Issues: {', '.join(issues)}")
                        return False
                else:
                    self.log_test("List Deals", False, f"Expected non-empty array, got: {type(data)} with length {len(data) if isinstance(data, list) else 'N/A'}")
                    return False
            else:
                self.log_test("List Deals", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("List Deals", False, f"Exception: {str(e)}")
            return False
            
    def test_deals_metrics(self):
        """Test 4: Metrics GET /api/deals/metrics - check required keys"""
        try:
            response = self.session.get(f"{BASE_URL}/deals/metrics")
            if response.status_code == 200:
                data = response.json()
                required_keys = ["count", "avg_multiple", "median_multiple", "by_sector", "by_geo"]
                missing_keys = [key for key in required_keys if key not in data]
                
                if not missing_keys:
                    self.log_test("Deals Metrics", True, f"All required keys present: {list(data.keys())}")
                    return True
                else:
                    self.log_test("Deals Metrics", False, f"Missing keys: {missing_keys}")
                    return False
            else:
                self.log_test("Deals Metrics", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("Deals Metrics", False, f"Exception: {str(e)}")
            return False
            
    def test_lbo_quick(self):
        """Test 5: LBO Quick POST /api/lbo/quick - expect positive MOIC and IRR"""
        try:
            payload = {
                "entry_ebitda": 50,
                "entry_ev_ebitda": 10,
                "revenue_growth": 0.08,
                "ebitda_margin": 0.2,
                "capex_pct_of_revenue": 0.04,
                "nwc_pct_change_of_revenue": 0.02,
                "interest_rate": 0.08,
                "leverage_multiple": 4,
                "exit_ev_ebitda": 9,
                "years": 5,
                "tax_rate": 0.25
            }
            
            response = self.session.post(f"{BASE_URL}/lbo/quick", json=payload)
            if response.status_code == 200:
                data = response.json()
                
                # Check for required fields
                required_fields = ["moic", "irr", "entry_ev", "entry_debt", "entry_equity", 
                                 "exit_ev", "exit_debt", "equity_value_at_exit", "yearly"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("LBO Quick", False, f"Missing fields: {missing_fields}")
                    return False
                
                # Check positive MOIC and IRR
                moic = data.get("moic", 0)
                irr = data.get("irr", 0)
                
                if moic > 0 and irr > 0:
                    self.log_test("LBO Quick", True, f"MOIC: {moic}, IRR: {irr}")
                    return True
                else:
                    self.log_test("LBO Quick", False, f"Expected positive MOIC and IRR, got MOIC: {moic}, IRR: {irr}")
                    return False
            else:
                self.log_test("LBO Quick", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
        except Exception as e:
            self.log_test("LBO Quick", False, f"Exception: {str(e)}")
            return False
            
    def test_deals_crud(self):
        """Test 6: Deals CRUD operations"""
        success_count = 0
        
        # CREATE - POST /api/deals
        try:
            create_payload = {
                "name": "Test Manufacturing Co",
                "sector": "Industrials",
                "subsector": "Manufacturing",
                "geography": "US",
                "revenue": 150.0,
                "ebitda": 30.0,
                "ebitda_margin": 0.20,
                "ev": 240.0,
                "growth_rate": 0.10,
                "net_debt": 50.0,
                "deal_stage": "sourced",
                "source": "test"
            }
            
            response = self.session.post(f"{BASE_URL}/deals", json=create_payload)
            if response.status_code == 200:
                data = response.json()
                if "id" in data:
                    self.created_deal_id = data["id"]
                    self.log_test("CRUD - Create Deal", True, f"Created deal with ID: {self.created_deal_id}")
                    success_count += 1
                else:
                    self.log_test("CRUD - Create Deal", False, "No ID in response")
            else:
                self.log_test("CRUD - Create Deal", False, f"Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            self.log_test("CRUD - Create Deal", False, f"Exception: {str(e)}")
            
        if not self.created_deal_id:
            self.log_test("CRUD Operations", False, "Cannot continue CRUD tests without created deal ID")
            return False
            
        # READ - GET /api/deals (should include our deal)
        try:
            response = self.session.get(f"{BASE_URL}/deals")
            if response.status_code == 200:
                data = response.json()
                found_deal = None
                for deal in data:
                    if deal.get("id") == self.created_deal_id:
                        found_deal = deal
                        break
                        
                if found_deal:
                    self.log_test("CRUD - Read Deal", True, f"Found created deal in list")
                    success_count += 1
                else:
                    self.log_test("CRUD - Read Deal", False, f"Created deal not found in list")
            else:
                self.log_test("CRUD - Read Deal", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("CRUD - Read Deal", False, f"Exception: {str(e)}")
            
        # UPDATE - PUT /api/deals/{id} - change ev and ensure ev_ebitda recomputed
        try:
            update_payload = {
                "ev": 300.0,  # Changed from 240.0
                "ebitda": 35.0  # Changed from 30.0
            }
            
            response = self.session.put(f"{BASE_URL}/deals/{self.created_deal_id}", json=update_payload)
            if response.status_code == 200:
                data = response.json()
                expected_ev_ebitda = 300.0 / 35.0  # Should be ~8.57
                actual_ev_ebitda = data.get("ev_ebitda")
                
                if actual_ev_ebitda and abs(actual_ev_ebitda - expected_ev_ebitda) < 0.1:
                    self.log_test("CRUD - Update Deal", True, f"ev_ebitda recomputed correctly: {actual_ev_ebitda}")
                    success_count += 1
                else:
                    self.log_test("CRUD - Update Deal", False, f"ev_ebitda not recomputed correctly. Expected ~{expected_ev_ebitda:.2f}, got {actual_ev_ebitda}")
            else:
                self.log_test("CRUD - Update Deal", False, f"Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            self.log_test("CRUD - Update Deal", False, f"Exception: {str(e)}")
            
        # DELETE - DELETE /api/deals/{id}
        try:
            response = self.session.delete(f"{BASE_URL}/deals/{self.created_deal_id}")
            if response.status_code == 200:
                # Verify it's deleted by trying to get the list again
                response = self.session.get(f"{BASE_URL}/deals")
                if response.status_code == 200:
                    data = response.json()
                    found_deal = any(deal.get("id") == self.created_deal_id for deal in data)
                    
                    if not found_deal:
                        self.log_test("CRUD - Delete Deal", True, f"Deal successfully deleted")
                        success_count += 1
                    else:
                        self.log_test("CRUD - Delete Deal", False, f"Deal still exists after deletion")
                else:
                    self.log_test("CRUD - Delete Deal", False, f"Could not verify deletion")
            else:
                self.log_test("CRUD - Delete Deal", False, f"Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            self.log_test("CRUD - Delete Deal", False, f"Exception: {str(e)}")
            
        return success_count == 4
        
    def test_csv_upload_flow(self):
        """Test 7: CSV upload flow - init->chunk->complete"""
        try:
            # Step 1: Initialize upload
            response = self.session.post(f"{BASE_URL}/upload/init")
            if response.status_code != 200:
                self.log_test("CSV Upload - Init", False, f"Init failed: {response.status_code}")
                return False
                
            upload_data = response.json()
            upload_id = upload_data.get("upload_id")
            if not upload_id:
                self.log_test("CSV Upload - Init", False, "No upload_id in response")
                return False
                
            self.log_test("CSV Upload - Init", True, f"Upload ID: {upload_id}")
            
            # Step 2: Upload chunk with small CSV
            csv_content = """name,sector,geography,revenue,ebitda,ev
TechCorp Alpha,Technology,US,100,25,200
HealthCare Beta,Healthcare,EU,80,16,144
Industrial Gamma,Industrials,US,120,18,162"""
            
            csv_file = io.BytesIO(csv_content.encode('utf-8'))
            
            files = {'chunk': ('test.csv', csv_file, 'text/csv')}
            data = {'upload_id': upload_id, 'index': 0}
            
            response = self.session.post(f"{BASE_URL}/upload/chunk", files=files, data=data)
            if response.status_code != 200:
                self.log_test("CSV Upload - Chunk", False, f"Chunk upload failed: {response.status_code}")
                return False
                
            self.log_test("CSV Upload - Chunk", True, "Chunk uploaded successfully")
            
            # Step 3: Complete upload
            data = {'upload_id': upload_id}
            response = self.session.post(f"{BASE_URL}/upload/complete", data=data)
            if response.status_code == 200:
                result = response.json()
                inserted = result.get("inserted", 0)
                
                if inserted > 0:
                    self.log_test("CSV Upload - Complete", True, f"Inserted {inserted} records")
                    return True
                else:
                    self.log_test("CSV Upload - Complete", False, f"No records inserted: {result}")
                    return False
            else:
                self.log_test("CSV Upload - Complete", False, f"Complete failed: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("CSV Upload Flow", False, f"Exception: {str(e)}")
            return False
            
    def run_all_tests(self):
        """Run all backend tests"""
        print(f"🚀 Starting Backend API Tests")
        print(f"Base URL: {BASE_URL}")
        print("=" * 60)
        
        tests = [
            self.test_health_endpoint,
            self.test_seed_endpoint,
            self.test_list_deals,
            self.test_deals_metrics,
            self.test_lbo_quick,
            self.test_deals_crud,
            self.test_csv_upload_flow
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                if test():
                    passed += 1
                print()  # Add spacing between tests
            except Exception as e:
                print(f"❌ Test failed with exception: {str(e)}")
                print()
                
        print("=" * 60)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed!")
            return True
        else:
            print(f"⚠️  {total - passed} tests failed")
            return False

if __name__ == "__main__":
    tester = BackendTester()
    success = tester.run_all_tests()
    
    if not success:
        exit(1)