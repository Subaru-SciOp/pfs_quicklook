# Troubleshooting Guide

This guide provides solutions to common issues you may encounter while using PFS QuickLook.

## Quick Diagnosis

### Application Won't Start

→ See [Launch Issues](#launch-issues)

### Can't Load Data

→ See [Data Loading Issues](#data-loading-issues)

### Plots Don't Appear or Look Wrong

→ See [Visualization Issues](#visualization-issues)

### Slow Performance

→ See [Performance Issues](#performance-issues)

### Interface Behaves Unexpectedly

→ See [User Interface Issues](#user-interface-issues)

---

## Launch Issues

### "Hostname mismatch" Error

**Symptom**: Launch script fails with message about hostname mismatch

**Cause**: The `PFS_APP_HOSTNAME` in `.env` doesn't match the actual server hostname

**Solutions**:

1. Check your current hostname:
   ```bash
   hostname -f
   ```

2. Edit `.env` file and update `PFS_APP_HOSTNAME`:
   ```bash
   vi .env
   # Update: PFS_APP_HOSTNAME=<output_from_hostname_-f>
   ```

3. Relaunch the application:
   ```bash
   bash ./launch_app.bash
   ```

**Prevention**: Always verify hostname in `.env` matches your server before launching

---

### Import Errors on Launch

**Symptom**: Python import errors when starting the application

**Common error messages**:
- `ModuleNotFoundError: No module named 'panel'`
- `ModuleNotFoundError: No module named 'holoviews'`
- `ImportError: cannot import name 'SpectrumSet'`

**Solutions**:

**For Panel/HoloViews errors**:
1. Verify LSST stack is loaded:
   ```bash
   source /work/stack/loadLSST.bash
   ```

2. Verify Python packages installed:
   ```bash
   ls /work/<your_username>/lsst-stack-local-pythonlibs/panel
   ```

3. If missing, reinstall packages:
   ```bash
   python3 -m pip install --target=/work/<your_username>/lsst-stack-local-pythonlibs -r requirements.txt
   ```

**For PFS/LSST errors**:
1. Ensure LSST stack environment is loaded
2. Check PFS pipeline setup:
   ```bash
   setup -v pfs_pipe2d
   setup -v display_matplotlib
   ```

**For persistent issues**:
- Check `LSST_PYTHON_USERLIB` in `.env` matches installation directory
- Verify launch script runs the correct Python: `which python3`
- Check launch script output for error messages

---

### Port Already in Use

**Symptom**: Error message: "Address already in use" or similar

**Cause**: Another instance of the application is already running on the same port

**Solutions**:

1. Check if application is running:
   ```bash
   ps aux | grep "panel serve"
   ```

2. Kill existing process:
   ```bash
   pkill -f "panel serve"
   ```

3. Relaunch application:
   ```bash
   bash ./launch_app.bash
   ```

**Alternative**: Change port in launch script if you need multiple instances

---

## Data Loading Issues

### No Visits Found

**Symptom**: Visit dropdown is empty

**Possible Causes & Solutions**:

**1. Wrong observation date**:
- Check configuration display in sidebar
- Verify `PFS_OBSDATE_UTC` in `.env`
- Try setting to `"TODAY"` if unsure

**2. Incorrect base collection**:
- Verify `PFS_BASE_COLLECTION` in `.env`
- Contact PFS obsproc team for correct collection name
- Collection format typically: `u/obsproc/<semester>/<date>` (e.g., `u/obsproc/s25a/20250520b`)

**3. No data for specified date**:
- Verify with data reduction team that data exists
- Check datastore directory for expected collections
- Try different observation date

**4. Datastore access issues**:
- Verify `PFS_DATASTORE` path in `.env` is correct
- Check you have read permissions:
  ```bash
  ls -la /work/datastore
  ```
- Contact administrator if permissions denied

**5. Initial discovery in progress**:
- First discovery can take 10-20 seconds
- Wait for completion (watch for toast notification)
- If no visits appear after 30 seconds, check Log tab for errors

---

### "Load Data" Button Doesn't Respond

**Symptom**: Clicking button has no effect

**Solutions**:

1. **Verify visit selected**: Ensure a visit is selected in dropdown

2. **Check browser console** for errors:
   - Press F12 to open developer tools
   - Click Console tab
   - Look for red error messages
   - Share errors with support if found

3. **Reload browser page**:
   - Press F5 or Ctrl+R (Cmd+R on Mac)
   - Reselect visit and try again

4. **Check WebSocket connection**:
   - In browser developer tools, check Network tab
   - Look for WebSocket connection (should show "Connected")
   - If disconnected, reload page or check network connectivity

---

### Slow Data Loading

**Symptom**: Loading takes longer than expected (>10 seconds)

**Expected times**:
- Visit data loading: 1-3 seconds
- Visit discovery: 10-20 seconds (first time)
- 2D image creation: 30-60 seconds for all selected spectrographs
- 1D spectra: 2-5 seconds

**Solutions**:

1. **Be patient on first load**:
   - First load after application restart may be slower
   - Subsequent loads benefit from caching

2. **Check network latency**:
   - Verify good network connection to server
   - VPN connections may be slower
   - Contact administrator if consistently slow

3. **Verify server not overloaded**:
   - Contact administrator to check server resources
   - Multiple concurrent users may slow performance

4. **For visit discovery**:
   - Initial discovery is slower (no cache)
   - Subsequent auto-refreshes are much faster (cached visits)
   - Date filtering improves performance

---

### Butler Configuration Errors

**Symptom**: Errors related to Butler, datastore, or collections

**Common messages**:
- "Cannot access datastore"
- "Collection not found"
- "Dataset type not found"

**Solutions**:

1. **Verify datastore path**:
   - Check `PFS_DATASTORE` in `.env`
   - Ensure path exists and is accessible
   - Verify permissions (should be readable by your user)

2. **Verify collection names**:
   - Check `PFS_BASE_COLLECTION` in `.env`
   - Confirm with PFS obsproc team
   - Ensure collection exists in Butler registry

3. **Check Butler manually**:
   ```bash
   butler query-collections /work/datastore
   ```
   - Look for your base collection
   - Verify subcollections exist (visit-specific)

4. **Contact data reduction team**:
   - If data should exist but isn't accessible
   - If collection names are unclear
   - If systematic Butler errors occur

---

## Visualization Issues

### 2D Images Don't Appear

**Symptom**: Blank or empty 2D Images tab after clicking "Plot 2D"

**Solutions**:

1. **Check Log tab** for error messages:
   - Click on Log tab in main panel
   - Look for error messages or stack traces
   - Note specific errors for support

2. **Verify data loaded**:
   - Check status display shows "Loaded visit XXXXX"
   - Ensure you clicked "Load Data" before "Plot 2D"

3. **Check for missing data products**:
   - Some visits may have incomplete data
   - Look for warning messages about missing arms
   - Contact data reduction team if data expected

4. **Reload and retry**:
   - Reload browser page (F5)
   - Load visit data again
   - Retry plotting

---

### 1D Spectra Don't Appear

**Symptom**: Empty or blank 1D Spectra tab after clicking "Plot 1D"

**Solutions**:

1. **Verify fiber selection**:
   - Ensure at least one fiber selected (OB Code or Fiber ID)
   - Check that selections appear in dropdowns
   - Try selecting different fibers

2. **Check legend visibility**:
   - Remember: Only first fiber visible by default
   - Click legend entries to show additional fibers
   - Look for muted (grayed-out) entries

3. **Check for error messages**:
   - Look in Log tab for errors
   - Check browser console (F12 → Console)
   - Report specific errors to support

4. **Verify data exists**:
   - Check that pfsMerged data exists for visit
   - Contact data reduction team if data missing
   - Try different visit

---

### Missing Arms in 2D Images

**Symptom**: Some arms don't appear in 2D Images tab

**This is usually normal**:
- Not all arms may be available for every visit
- Data reduction may skip certain arms
- Check informational note below plots for details

**When to investigate**:
- If arms expected to be available are missing
- If all arms missing for a spectrograph
- If systematic pattern across visits

**Actions**:
- Note which arms are missing
- Check with data reduction team
- Verify in data reduction logs

---

### Images Appear Corrupted or Strange

**Symptom**: Images show unusual patterns, colors, or artifacts

**Solutions**:

1. **Try different browser**:
   - Test in Chrome, Firefox, or Safari
   - WebGL compatibility varies by browser
   - Report which browsers work/don't work

2. **Check browser zoom**:
   - Reset browser zoom to 100% (Ctrl+0 or Cmd+0)
   - Extreme zoom levels may cause rendering issues

3. **Clear browser cache**:
   - Clear cache and reload page
   - Cached JavaScript may be outdated

4. **Verify data quality**:
   - Check if problem persists with different visits
   - If specific to one visit, may be data issue
   - Consult with data reduction team

---

### Hover Tooltips Don't Appear

**Symptom**: Moving mouse over plots doesn't show tooltips

**Solutions**:

1. **Enable hover tool**:
   - Check Bokeh toolbar on plot
   - Click hover tool icon to activate
   - Ensure hover tool is not disabled

2. **Move mouse slowly**:
   - Tooltips may not appear with rapid movement
   - Hover over plot and pause briefly

3. **Check browser compatibility**:
   - Some browsers may have tooltip issues
   - Try different browser
   - Update browser to latest version

4. **Reload page**:
   - Press F5 to reload
   - Recreate plots
   - Try hover again

---

## Performance Issues

### Very Slow 2D Rendering

**Symptom**: 2D image rendering takes much longer than expected

**Expected times**:
- Typically 30-60 seconds for all selected spectrographs
- Time varies based on number of spectrographs and arms selected

**Solutions**:

1. **Reduce number of spectrographs**:
   - Deselect unneeded spectrographs before plotting
   - Fewer spectrographs = faster rendering

2. **Check server load**:
   - Contact administrator if consistently slow
   - Server may be under heavy load
   - Multiple concurrent users affect performance

3. **Verify network connection**:
   - Slow network to datastore affects loading
   - VPN connections may be slower
   - Test network speed

---

### Slow Visit Discovery

**Symptom**: Visit discovery takes very long (>30 seconds)

**Normal behavior**:
- First discovery: 10-20 seconds (no cache)
- Subsequent refreshes: <5 seconds (with cache)

**Solutions**:

1. **Be patient on first run**:
   - Initial discovery always slower
   - Builds cache for future use
   - Subsequent refreshes much faster

2. **Verify date filtering enabled**:
   - Check `PFS_OBSDATE_UTC` is set in `.env`
   - Date filtering dramatically improves performance
   - Without filtering, must check all visits

3. **Check network to datastore**:
   - Network latency affects discovery time
   - Test connection to datastore
   - Contact administrator if network issues

4. **Reduce refresh frequency**:
   - Edit `PFS_VISIT_REFRESH_INTERVAL` in `.env`
   - Increase interval (e.g., 600 seconds)
   - Or set to 0 to disable auto-refresh

---

### Laggy Plot Interaction

**Symptom**: Slow response to pan, zoom, or hover in plots

**Solutions**:

1. **Reduce number of plotted fibers**:
   - For 1D plots, plot fewer fibers at once
   - Mute fibers you're not examining

2. **Close other browser tabs**:
   - Free up browser memory
   - Reduce CPU usage

3. **Refresh browser page**:
   - Clear accumulated JavaScript state
   - Reload and recreate plots

4. **Update browser**:
   - Ensure latest browser version
   - Newer versions have better performance

---

## User Interface Issues

### Widget Not Updating

**Symptom**: Dropdown selections or buttons don't respond

**Solutions**:

1. **Reload browser page**:
   - Press F5 or Ctrl+R (Cmd+R on Mac)
   - Resets session state
   - Often resolves widget issues

2. **Check JavaScript errors**:
   - Open browser console (F12)
   - Look for errors
   - Share with support if found

3. **Clear browser cache**:
   - May help with persistent widget issues
   - Reload page after clearing

4. **Try different browser**:
   - Test if issue is browser-specific
   - Chrome and Firefox recommended

---

### Fiber Selection Not Syncing

**Symptom**: OB Code and Fiber ID selections don't synchronize

**Expected behavior**:
- Selecting OB Code → Fiber IDs auto-populate
- Selecting Fiber ID → OB Codes auto-populate
- Bidirectional synchronization

**Solutions**:

1. **Clear selections and try again**:
   - Click "Reset" button
   - Reload visit data
   - Try selecting again

2. **Reload browser page**:
   - F5 or Ctrl+R to reload
   - Load visit data
   - Test synchronization

3. **Check Log tab**:
   - Look for JavaScript errors
   - Report to support if errors found

---

### Configuration Display Wrong

**Symptom**: Configuration display shows incorrect or outdated values

**Solutions**:

1. **Reload browser page**:
   - Configuration loaded on session start
   - Reload (F5) to refresh
   - Values should update

2. **Verify server .env file**:
   - Ask administrator to check `.env` file
   - Ensure values are correct on server
   - Configuration display shows server settings, not local

3. **Check for multiple servers**:
   - Ensure you're connected to correct server
   - Verify hostname in URL matches expected server

---

### Plots Disappear Unexpectedly

**Symptom**: Plots that were visible suddenly disappear

**Causes**:
- Loading new visit data clears all plots
- Clicking Reset button clears plots
- This is expected behavior

**To preserve plots**:
- Don't load new visit until done with current plots
- Open multiple browser tabs for comparing visits
- Take screenshots before loading new data

---

### Toast Notifications Don't Appear

**Symptom**: No feedback messages (toasts) shown

**Normal behavior**:
- Toasts appear for important events (loading, errors, warnings)
- Auto-dismiss after a few seconds

**If no toasts appear**:
1. Check browser notification settings (may be blocked)
2. Check browser console for errors
3. Functionality may still work even without toasts

---

## Browser-Specific Issues

### Firefox WebGL Errors

**Symptom**: JavaScript errors related to WebGL in Firefox

**Known issue**: Firefox WebGL compatibility, especially over VPN

**Solutions**:
1. This is normal - application disables WebGL by default for compatibility
2. No action needed unless plots don't appear
3. If plots don't appear, try Chrome or Brave

---

### Safari Compatibility

**Symptom**: Issues specific to Safari browser

**Recommendations**:
- Chrome and Firefox are primary tested browsers
- Safari should work but may have minor issues
- Report Safari-specific issues to support
- Consider using Chrome/Firefox for best experience

---

## Getting Additional Help

### Before Contacting Support

Gather the following information:

1. **What you were doing**: Step-by-step actions
2. **Expected behavior**: What should have happened
3. **Actual behavior**: What actually happened
4. **Error messages**: From UI, Log tab, or browser console
5. **Visit number**: If issue is visit-specific
6. **Browser**: Type and version
7. **Screenshots**: If visual issue

### Check Logs

**Application Log tab**:
- Click Log tab in main panel
- Look for error messages
- Copy relevant messages for support

**Browser Console**:
- Press F12 to open developer tools
- Click Console tab
- Look for red error messages
- Copy full error text and stack trace

### Contact Information

**PFS Observation Helpdesk**:
- Email: <pfs-obs-help@naoj.org>
- Provide all information gathered above

**GitHub Issues**:
- Create issue: <https://github.com/Subaru-SciOp/pfs_quicklook/issues>
- Search existing issues first
- Include detailed problem description

**Administrator**:
- Contact your local PFS QuickLook administrator
- For server-side issues (configuration, installation, etc.)

---

## See Also

- [Setup Guide](setup.md) - For installation and configuration issues
- [User Guide](user-guide/index.md) - For usage questions
- [CLAUDE.md](../CLAUDE.md) - Technical documentation and known limitations
