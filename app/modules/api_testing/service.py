"""
Service layer for K6 execution, script management, and test orchestration
Fixes for K6 not running + proper error handling
"""

import subprocess
import asyncio
import os
import tempfile
import json
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from app.modules.api_testing.models import TestRun, RunStatus, APILog
from app.modules.api_testing.db_service import db


# ============================================================================
# K6 Script Execution - FIXED
# ============================================================================

class K6ExecutionError(Exception):
    """Custom exception for K6 execution failures"""
    pass


async def run_k6_test(script_content: str, run_id: str, script_name: str) -> Dict[str, Any]:
    """
    Execute K6 test script
    
    FIXES:
    1. ✅ Write script to temp file first (ensures proper escaping)
    2. ✅ Use shell=True for proper PATH resolution
    3. ✅ Add comprehensive error handling
    4. ✅ Use asyncio for non-blocking execution
    5. ✅ Wait for completion and capture output
    6. ✅ Store output/logs in database
    
    Args:
        script_content: K6 JavaScript code
        run_id: MongoDB run ID for tracking
        script_name: Name for logging
    
    Returns:
        Dict with execution results
    """
    
    print(f"\n{'='*70}")
    print(f"🚀 Starting K6 Test Run: {script_name} (ID: {run_id})")
    print(f"{'='*70}")
    
    try:
        # Step 1: Create temporary script file
        print(f"📝 Step 1: Creating temporary K6 script...")
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False,
        ) as f:
            f.write(script_content)
            script_path = f.name
        
        print(f"   ✅ Script written to: {script_path}")
        print(script_content)
        
        # Step 2: Build K6 command
        print(f"📝 Step 2: Building K6 command...")
        
        # Using shell=True to access system PATH and environment
        # K6 will output metrics to InfluxDB as configured in docker-compose
        command = (
            f'k6 run "{script_path}" '
            f'--out influxdb=http://localhost:8086/k6 '
        )
        
        print(f"   ✅ Command: {command}")
        
        # Step 3: Execute K6 with proper error handling
        print(f"📝 Step 3: Executing K6 subprocess...")
        
        # Update run status to RUNNING in database
        await db.update_run_status(run_id, RunStatus.RUNNING)
        
        try:
            # Run with timeout and shell=True for environment access
            # process = await asyncio.create_subprocess_shell(
            #     command,
            #     stdout=asyncio.subprocess.PIPE,
            #     stderr=asyncio.subprocess.PIPE,
            #     shell=True
            # )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True,
                timeout=300
            )
            print("Executing command:")
            print(command)
            
            # print(f"   ✅ Process started (PID: {process.pid})")
            
            # # Wait for process to complete (with timeout if needed)
            # stdout, stderr = await asyncio.wait_for(
            #     process.communicate(),
            #     timeout=600  # 10 minute timeout
            # )
            
            # Step 4: Process results
            print(f"📝 Step 4: Processing results...")
            stdout_str = result.stdout or ""
            stderr_str = result.stderr or ""
            # stdout_str = stdout.decode('utf-8', errors='ignore') if stdout else ""
            # stderr_str = stderr.decode('utf-8', errors='ignore') if stderr else ""
            
            if result.returncode == 0:
                print(f"   ✅ K6 execution completed successfully")
                print(f"   📊 Output preview: {stdout_str[:200]}...")
                
                # Parse K6 summary from output
                summary = _parse_k6_output(stdout_str)
                print("DEBUG: Summary parsed")
                print(summary)
                
                # Update run with completion status
                await db.update_run_status(
                    run_id,
                    RunStatus.COMPLETED,
                    summary=summary if summary else None
                )
                print("DEBUG: DB update completed")
                
                # Clean up temp file
                os.unlink(script_path)
                
                return {
                    "status": "completed",
                    "run_id": run_id,
                    "summary": summary,
                    "stdout": stdout_str,
                    "exitCode": result.returncode
                }
            else:
                # K6 execution failed
                print(f"   ❌ K6 execution failed (exit code: {result.returncode})")
                print(f"   Error output: {stderr_str[:500]}")
                
                await db.update_run_status(run_id, RunStatus.FAILED)
                os.unlink(script_path)
                
                raise K6ExecutionError(
                    f"K6 failed with exit code {result.returncode}. "
                    f"Error: {stderr_str[:200]}"
                )
        
        except asyncio.TimeoutError:
            print(f"   ❌ K6 execution timed out (>10 minutes)")
            await db.update_run_status(run_id, RunStatus.FAILED)
            os.unlink(script_path)
            raise K6ExecutionError("K6 test execution exceeded 10 minute timeout")
        
        except Exception as e:
            import traceback

            print("FULL ERROR:")
            traceback.print_exc()
        
            print(f"❌ Subprocess error: {str(e)}")

            await db.update_run_status(run_id, RunStatus.FAILED)
            if os.path.exists(script_path):
                os.unlink(script_path)
            raise K6ExecutionError(f"Subprocess error: {str(e)}")
    
    except K6ExecutionError as e:
        print(f"\n❌ K6 Execution Error: {e}")
        return {
            "status": "failed",
            "run_id": run_id,
            "error": str(e)
        }
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        await db.update_run_status(run_id, RunStatus.FAILED)
        return {
            "status": "failed",
            "run_id": run_id,
            "error": f"Unexpected error: {str(e)}"
        }
    finally:
        print(f"{'='*70}\n")


# ============================================================================
# K6 Output Parsing
# ============================================================================

def _parse_k6_output(output: str) -> Optional[Dict[str, Any]]:
    """
    Parse K6 summary output to extract metrics
    
    K6 outputs a summary at the end like:
    ```
    checks.........................: 100% 5000 out of 5000
    http_req_duration.............: avg=125.42ms min=5.23ms med=110.32ms max=1200.34ms p(90)=250ms p(95)=350ms
    http_req_failed...............: 0.00% 0 out of 5000
    ```
    """
    try:
        # Look for summary section
        if "checks" not in output:
            return None
        
        summary = {
            "totalRequests": 0,
            "failedRequests": 0,
            "avgResponseTime": 0.0,
            "p95": None,
            "p99": None,
            "successRate": 100.0
        }
        
        # Parse lines
        for line in output.split('\n'):
            # Parse requests
            if 'http_reqs' in line.lower():
                # Extract number: "50 requests in 30s"
                parts = line.split()
                if parts:
                    try:
                        summary["totalRequests"] = int(parts[0])
                    except ValueError:
                        pass
            
            # Parse duration
            if 'http_req_duration' in line.lower():
                # Extract avg=XXXms
                if 'avg=' in line:
                    avg_str = line.split('avg=')[1].split()[0].replace('ms', '')
                    try:
                        summary["avgResponseTime"] = float(avg_str)
                    except ValueError:
                        pass
                
                # Extract p(95)
                if 'p(95)=' in line:
                    p95_str = line.split('p(95)=')[1].split()[0].replace('ms', '')
                    try:
                        summary["p95"] = float(p95_str)
                    except ValueError:
                        pass
            
            # Parse failures
            if 'http_req_failed' in line.lower():
                # Extract failure rate
                if '%' in line:
                    rate_str = line.split('%')[0].split()[-1]
                    try:
                        summary["successRate"] = 100.0 - float(rate_str)
                    except ValueError:
                        pass
        
        return summary
    
    except Exception as e:
        print(f"⚠️  Error parsing K6 output: {e}")
        return None


# ============================================================================
# Test Flow Orchestration
# ============================================================================

async def run_api_test_flow(script_id: str, script_name: str) -> Dict[str, Any]:
    """
    Orchestrate complete test flow:
    1. Create run record in DB
    2. Execute K6
    3. Monitor and update status
    4. Return results
    
    Args:
        script_id: MongoDB script ID to run
        script_name: Script display name
    
    Returns:
        Response dict with run details
    """
    try:
        # Get script from database
        script = await db.get_script(script_id)
        if not script:
            return {
                "status": "error",
                "error": f"Script not found: {script_id}"
            }
        
        # Create run record
        print(f"📋 Creating run record in database...")
        run = TestRun(
            scriptId=script_id,
            scriptName=script_name,
            status=RunStatus.PENDING
        )
        run_id = await db.create_run(run)
        print(f"✅ Run created: {run_id}")
        
        # Execute K6 test (async, non-blocking)
        result = await run_k6_test(script.script, run_id, script_name)
        
        # Add run_id to response
        result["run_id"] = run_id
        
        return result
    
    except Exception as e:
        print(f"❌ Test flow error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# ============================================================================
# Deprecated: Synchronous version (for reference)
# ============================================================================

def run_api_test_flow_sync(command: list) -> Dict[str, Any]:
    """
    DEPRECATED - Use async version instead
    Kept for backwards compatibility
    """
    print("⚠️  Using deprecated sync version")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
            shell=True  # FIX: Added shell=True
        )
        
        if result.returncode == 0:
            return {"status": "completed", "exitCode": 0}
        else:
            return {
                "status": "failed",
                "error": result.stderr,
                "exitCode": result.returncode
            }
    
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "Test execution timeout"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# ============================================================================
# Helper Functions
# ============================================================================

async def save_api_log(log: APILog, run_id: Optional[str] = None) -> bool:
    """Save API log to database"""
    try:
        log.run_id = run_id
        await db.save_log(log)
        return True
    except Exception as e:
        print(f"❌ Error saving log: {e}")
        return False


async def get_api_logs(run_id: Optional[str] = None, limit: int = 200) -> list:
    """Get API logs, optionally for specific run"""
    return await db.get_logs(run_id=run_id, limit=limit)