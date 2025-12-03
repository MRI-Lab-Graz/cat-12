function run_tfce_correction(stats_folder, varargin)
% RUN_TFCE_CORRECTION - Run TFCE multiple comparison correction
%
% This function runs TFCE (Threshold-Free Cluster Enhancement) correction
% on contrasts from a statistical analysis. Can run on all contrasts or
% only those that passed screening.
%
% Usage:
%   run_tfce_correction(stats_folder)
%   run_tfce_correction(stats_folder, 'n_perm', 5000, 'use_screening', true)
%
% Inputs:
%   stats_folder     - Path to SPM.mat directory
%   'n_perm'         - Number of permutations (default: 5000)
%   'n_jobs'         - Parallel jobs (default: 4)
%   'use_screening'  - Only process contrasts that passed screening (default: true)
%   'contrast_list'  - Specific contrast indices to process (overrides screening)
%   'pilot'          - Test mode: only 1 random contrast (default: false)
%
% Outputs:
%   Creates TFCE_<contrast>/ directories with corrected results
%
% Example:
%   run_tfce_correction('/path/to/stats/s9_int_control', 'n_perm', 5000);

% Parse inputs
p = inputParser;
addRequired(p, 'stats_folder', @ischar);
addParameter(p, 'n_perm', 5000, @isnumeric);
addParameter(p, 'n_jobs', 4, @isnumeric);
addParameter(p, 'use_screening', true, @islogical);
addParameter(p, 'contrast_list', [], @isnumeric);
addParameter(p, 'pilot', false, @islogical);
addParameter(p, 'force', false, @islogical);
addParameter(p, 'nuisance_method', '', @ischar);
addParameter(p, 'config_file', '', @ischar);
parse(p, stats_folder, varargin{:});

stats_folder = p.Results.stats_folder;
n_perm = p.Results.n_perm;
n_jobs = p.Results.n_jobs;
use_screening = p.Results.use_screening;
contrast_list = p.Results.contrast_list;
pilot_mode = p.Results.pilot;
force_analysis = p.Results.force;

% Load configuration
config_file = '';
if isfield(p.Results, 'config_file')
    config_file = p.Results.config_file;
end

config = struct();
config.tfce = struct();
config.performance = struct();

if ~isempty(config_file) && exist(config_file, 'file')
    fprintf('Loading configuration from: %s\n', config_file);
    config = read_config_ini(config_file);
end

% Override defaults with config values if they exist
if isfield(config, 'tfce')
    if isfield(config.tfce, 'n_perm') && isempty(p.Results.n_perm)
        n_perm = config.tfce.n_perm;
    end
    if isfield(config.performance, 'parallel_jobs') && isempty(p.Results.n_jobs)
        n_jobs = config.performance.parallel_jobs;
    end
    if isfield(config.tfce, 'pilot_mode') && isempty(p.Results.pilot)
        pilot_mode = config.tfce.pilot_mode;
    end
end

% Add shadow functions to path FIRST (prevents GUI)
script_dir = fileparts(fileparts(mfilename('fullpath')));  % Go up to stats/
tfce_dir = fullfile(script_dir, 'archive', '06_tfce');
addpath(tfce_dir, '-begin');

fprintf('\n%s\n', repmat('═', 1, 80));
fprintf('TFCE MULTIPLE COMPARISON CORRECTION\n');
fprintf('%s\n\n', repmat('═', 1, 80));

% Load SPM.mat
spm_mat_file = fullfile(stats_folder, 'SPM.mat');
if ~exist(spm_mat_file, 'file')
    error('SPM.mat not found in: %s', stats_folder);
end

load(spm_mat_file, 'SPM');
n_total_contrasts = length(SPM.xCon);

% Determine which contrasts to process
if ~isempty(contrast_list)
    % User specified contrasts
    contrasts_to_process = contrast_list;
    fprintf('Processing user-specified contrasts: %d contrasts\n', ...
            length(contrasts_to_process));
    
elseif use_screening
    % Use screening results
    screening_file = fullfile(stats_folder, 'screening_results.mat');
    if ~exist(screening_file, 'file')
        error(['Screening results not found. Run screen_contrasts() first ' ...
               'or set use_screening=false']);
    end
    
    load(screening_file, 'significant_contrasts');
    contrasts_to_process = significant_contrasts;
    
    fprintf('Using screening results:\n');
    fprintf('  Total contrasts:       %d\n', n_total_contrasts);
    fprintf('  Significant contrasts: %d\n', length(contrasts_to_process));
    fprintf('  Processing:            %.1f%%\n\n', ...
            100 * length(contrasts_to_process) / n_total_contrasts);
else
    % Process all contrasts
    contrasts_to_process = 1:n_total_contrasts;
    fprintf('Processing ALL contrasts: %d\n\n', n_total_contrasts);
end

if pilot_mode
    % Pilot mode: select 1 random contrast
    if isempty(contrasts_to_process)
         fprintf('🧪 PILOT MODE: No significant contrasts found. Falling back to random selection from ALL contrasts.\n');
         contrasts_to_process = 1:n_total_contrasts;
    else
         fprintf('🧪 PILOT MODE: Selecting from %d significant contrasts.\n', length(contrasts_to_process));
    end

    rng('shuffle');
    if ~isempty(contrasts_to_process)
        % Shuffle the list to pick a random starting point
        % We will iterate through them and STOP after the first success.
        shuffled_indices = contrasts_to_process(randperm(length(contrasts_to_process)));
        contrasts_to_process = shuffled_indices;
        fprintf('🧪 PILOT MODE: Will attempt contrasts in random order until one succeeds.\n');
        fprintf('   First candidate: Contrast #%d\n\n', contrasts_to_process(1));
    else
        fprintf('🧪 PILOT MODE: No contrasts available to process.\n');
    end
end

fprintf('TFCE Parameters:\n');
fprintf('  Permutations:  %d\n', n_perm);
fprintf('  Parallel jobs: %d\n', n_jobs);
fprintf('  Contrasts:     %d\n\n', length(contrasts_to_process));

% Initialize SPM
spm('defaults', 'FMRI');
spm_jobman('initcfg');

% Process each contrast
fprintf('%s\n', repmat('─', 1, 80));
fprintf('Running TFCE correction:\n');
fprintf('%s\n\n', repmat('─', 1, 80));

tfce_success = 0;
tfce_skipped = 0;
tfce_failed = 0;

for i = 1:length(contrasts_to_process)
    con_idx = contrasts_to_process(i);
    con_name = SPM.xCon(con_idx).name;
    
    fprintf('[%d/%d] Contrast %d: %s\n', i, length(contrasts_to_process), ...
            con_idx, con_name);
    
    % Check if TFCE already exists
    tfce_folder = fullfile(stats_folder, sprintf('TFCE_%04d', con_idx));
    if exist(tfce_folder, 'dir') && ~force_analysis
        if exist(fullfile(tfce_folder, 'logP_max.nii'), 'file') || exist(fullfile(tfce_folder, 'logP_max.gii'), 'file')
            fprintf('        ⊙ TFCE results already exist, skipping\n\n');
            tfce_skipped = tfce_skipped + 1;
            continue;
        end
    end
    
    % Prepare TFCE job per user's TFCE GUI layout requirements
    % (no exchangeability in batch; explicit SPM.mat, contrast index, title,
    % mask, multi-threading on, TBSS off).
    clear matlabbatch;
    % Provide SPM.mat explicitly
    matlabbatch{1}.spm.tools.tfce_estimate.data = {spm_mat_file};
    % Parallel jobs
    matlabbatch{1}.spm.tools.tfce_estimate.nproc = n_jobs;
    % Mask: prefer canonical repo template mask
    % Check if we are working with GIfTI files (surface data)
    is_surface = false;
    if isfield(SPM.xY, 'VY') && ~isempty(SPM.xY.VY)
        [~,~,ext] = fileparts(SPM.xY.VY(1).fname);
        if strcmpi(ext, '.gii')
            is_surface = true;
        end
    elseif ~isempty(dir(fullfile(stats_folder, '*.gii')))
         is_surface = true;
    end

    if is_surface
        fprintf('        Surface data detected: disabling volumetric mask.\n');
        matlabbatch{1}.spm.tools.tfce_estimate.mask = '';
    else
        utils_dir = fileparts(fileparts(mfilename('fullpath')));
        template_mask = fullfile(utils_dir, 'templates', 'brainmask_GMtight.nii');
        if exist(template_mask, 'file')
            matlabbatch{1}.spm.tools.tfce_estimate.mask = {template_mask};
        else
            matlabbatch{1}.spm.tools.tfce_estimate.mask = '';
        end
    end
    % Contrast query
    matlabbatch{1}.spm.tools.tfce_estimate.conspec.titlestr = con_name; % results title
    matlabbatch{1}.spm.tools.tfce_estimate.conspec.contrasts = con_idx; % contrast index
    
    % Permutations (with optional early break)
    if isfield(config.tfce, 'n_perm_break') && config.tfce.n_perm_break > 0
        matlabbatch{1}.spm.tools.tfce_estimate.conspec.n_perm = [n_perm, config.tfce.n_perm_break];
        fprintf('  Permutation break: %d\n', config.tfce.n_perm_break);
    else
        matlabbatch{1}.spm.tools.tfce_estimate.conspec.n_perm = n_perm;
    end
    
    % Nuisance method
    % Map human-friendly names to TFCE numeric codes.
    nuisance_method_str = 'smith'; % default
    if isfield(config.tfce, 'nuisance_method')
        nuisance_method_str = lower(config.tfce.nuisance_method);
    end
    % Allow user override via function parameter
    if isfield(p.Results, 'nuisance_method') && ~isempty(p.Results.nuisance_method)
        nuisance_method_str = lower(p.Results.nuisance_method);
    end
    switch nuisance_method_str
        case {'smith','2'}
            nuisance_val = 2;
        case {'draper-stoneman','draper_stoneman','draper','0'}
            nuisance_val = 0;
        case {'freedman-lane','freedman_lane','freedman','1'}
            nuisance_val = 1;
        otherwise
            warning('Invalid nuisance_method "%s" in config.ini. Defaulting to "smith".', nuisance_method_str);
            nuisance_val = 2;
    end
    matlabbatch{1}.spm.tools.tfce_estimate.nuisance_method = nuisance_val;

    % TBSS flag
    tbss_flag = false; % default
    if isfield(config.tfce, 'tbss')
        tbss_flag = config.tfce.tbss;
    end
    matlabbatch{1}.spm.tools.tfce_estimate.tbss = double(tbss_flag);

    % Multi-threading (singlethreaded = 0 for multi, 1 for single)
    multi_threading_flag = true; % default
    if isfield(config.tfce, 'multi_threading')
        multi_threading_flag = config.tfce.multi_threading;
    end
    matlabbatch{1}.spm.tools.tfce_estimate.singlethreaded = double(~multi_threading_flag);
    
    try
        fprintf('        Running TFCE (%d permutations)...\n', n_perm);

        % Before running: save the prepared batch for inspection and
        % validate required fields. This prevents calling TFCE with an
        % incomplete/undefined batch (which some TFCE versions reject).
        try
            logs_dir = fullfile(stats_folder, 'logs');
            if ~exist(logs_dir, 'dir')
                mkdir(logs_dir);
            end
            prepared_batch_file = fullfile(logs_dir, sprintf('tfce_prepared_batch_contrast_%04d.mat', con_idx));
            % Save the matlabbatch as-is for offline inspection
            try
                save(prepared_batch_file, 'matlabbatch');
                fprintf('        Saved prepared batch to: %s\n', prepared_batch_file);
            catch MEsave
                fprintf('        ⚠ Could not save prepared batch: %s\n', MEsave.message);
            end

            % Basic validation of required fields expected by TFCE toolbox
            valid = true;
            diag_msgs = {};

            % data: expect a non-empty cell array of filenames (SPM.mat)
            % or accept '<UNDEFINED>' string (legacy templates)
            try
                dataf = matlabbatch{1}.spm.tools.tfce_estimate.data;
                if ischar(dataf)
                    % exact '<UNDEFINED>' placeholder is acceptable
                    if ~strcmp(dataf, '<UNDEFINED>')
                        valid = false;
                        diag_msgs{end+1} = 'data field is a string but not ''<UNDEFINED>'' (unexpected)';
                    end
                elseif iscell(dataf)
                    if isempty(dataf) || any(cellfun(@(x) isempty(x) || (ischar(x) && strcmp(x,'<UNDEFINED>')), dataf))
                        valid = false;
                        diag_msgs{end+1} = 'data field is a cell but empty or contains <UNDEFINED> placeholders';
                    end
                else
                    valid = false;
                    diag_msgs{end+1} = 'data field has unexpected type (expected ''<UNDEFINED>'' or cell of filenames)';
                end
            catch
                valid = false;
                diag_msgs{end+1} = 'data field is missing from matlabbatch';
            end

            % mask: allow empty string '' (template) or a cell array of filename(s)
            try
                if isfield(matlabbatch{1}.spm.tools.tfce_estimate, 'mask')
                    maskf = matlabbatch{1}.spm.tools.tfce_estimate.mask;
                    if ischar(maskf)
                        % empty string '' is acceptable
                        if ~isempty(maskf)
                            % Non-empty string — warn but accept (could be filename)
                        end
                    elseif iscell(maskf)
                        if isempty(maskf) || any(cellfun(@(x) isempty(x), maskf))
                            valid = false;
                            diag_msgs{end+1} = 'mask field is a cell but empty or contains empty entries';
                        end
                    else
                        valid = false;
                        diag_msgs{end+1} = 'mask field has unexpected type';
                    end
                end
            catch
                valid = false;
                diag_msgs{end+1} = 'mask field check failed';
            end

            % conspec.titlestr (string), conspec.contrasts (numeric index) and conspec.n_perm
            try
                cons = matlabbatch{1}.spm.tools.tfce_estimate.conspec;
                if ~isfield(cons, 'titlestr') || ~ischar(cons.titlestr)
                    valid = false;
                    diag_msgs{end+1} = 'conspec.titlestr missing or not a char array';
                end
                if ~isfield(cons, 'contrasts') || isempty(cons.contrasts) || ~isnumeric(cons.contrasts)
                    valid = false;
                    diag_msgs{end+1} = 'conspec.contrasts missing or not numeric';
                end
                if ~isfield(cons, 'n_perm') || isempty(cons.n_perm) || ~isnumeric(cons.n_perm)
                    valid = false;
                    diag_msgs{end+1} = 'conspec.n_perm missing or not numeric';
                end
            catch
                valid = false;
                diag_msgs{end+1} = 'conspec field missing or malformed';
            end

            % conspec.exchangeability: explicitly disallow — some TFCE versions
            % reject an exchangeability field in the batch. If present, fail.
            try
                if isfield(matlabbatch{1}.spm.tools.tfce_estimate.conspec, 'exchangeability')
                    valid = false;
                    diag_msgs{end+1} = 'conspec.exchangeability is present in batch but is not allowed for this TFCE toolbox/version';
                end
            catch
                valid = false;
                diag_msgs{end+1} = 'error checking conspec.exchangeability';
            end

            % If validation failed, write diagnostics and skip this contrast
            if ~valid
                diag_file = fullfile(logs_dir, sprintf('tfce_prepared_batch_contrast_%04d.diag.txt', con_idx));
                fid = fopen(diag_file, 'w');
                if fid ~= -1
                    fprintf(fid, 'TFCE prepared batch validation FAILED for contrast %d\n\n', con_idx);
                    for d = 1:length(diag_msgs)
                        fprintf(fid, '%s\n', diag_msgs{d});
                    end
                    fclose(fid);
                end
                fprintf('        ✗ Prepared batch validation FAILED for contrast %d. See %s and %s\n\n', con_idx, prepared_batch_file, diag_file);
                tfce_failed = tfce_failed + 1;
                continue;
            end

            % Print debug information about the contrast and design so
            % it's recorded in the logs for later diagnosis.
            try
                con_struct = SPM.xCon(con_idx);
                % contrast vector/matrix shape
                if isfield(con_struct, 'c')
                    cc = con_struct.c;
                    try
                        sz = size(cc);
                        fprintf('        Contrast c shape: [%s]\n', sprintf('%d ', sz));
                    catch
                        fprintf('        Contrast c: (unable to determine shape)\n');
                    end
                    try
                        nnz_c = sum(cc(:) ~= 0);
                        fprintf('        Contrast nonzero elements: %d\n', nnz_c);
                    catch
                    end
                end
                if isfield(con_struct, 'STAT')
                    fprintf('        Contrast STAT: %s\n', con_struct.STAT);
                end
            catch
                fprintf('        (Could not read contrast structure for logging)\n');
            end

            % Print factor summary (names and levels) if available
            try
                if isfield(SPM, 'factor')
                    fac = SPM.factor;
                    if iscell(fac) || isa(fac, 'struct') || numel(fac) > 0
                        % iterate factors
                        for ff = 1:numel(fac)
                            try
                                fname = fac(ff).name;
                                flevs = fac(ff).levels;
                                fprintf('        Factor %d: %s (levels=%d)\n', ff, fname, flevs);
                            catch
                                % ignore per-factor failures
                            end
                        end
                    end
                end
            catch
                % ignore
            end

            % Run TFCE via SPM batch runner to ensure toolbox receives the
            % matlabbatch (which now includes exchangeability if available).
            try
                spm_jobman('run', matlabbatch);

                % Verify expected outputs exist. Different TFCE toolbox
                % versions write outputs either into a per-contrast folder
                % (e.g. TFCE_0002/logP_max.nii) or into the stats folder
                % with names like TFCE_0002.nii / TFCE_log_pFWE_0002.nii. We
                % accept either pattern as success to avoid false negatives.
                
                % Wait a moment for filesystem to sync (external drives can be slow)
                pause(2);
                
                tfce_folder_ok = exist(tfce_folder, 'dir') && (exist(fullfile(tfce_folder, 'logP_max.nii'), 'file') || exist(fullfile(tfce_folder, 'logP_max.gii'), 'file'));
                alt_out1 = fullfile(stats_folder, sprintf('TFCE_%04d.nii', con_idx));
                alt_out2 = fullfile(stats_folder, sprintf('TFCE_log_pFWE_%04d.nii', con_idx));
                alt_out3 = fullfile(stats_folder, sprintf('TFCE_log_p_%04d.nii', con_idx));
                alt_out4 = fullfile(stats_folder, sprintf('TFCE_log_pFDR_%04d.nii', con_idx));
                
                alt_out1_gii = fullfile(stats_folder, sprintf('TFCE_%04d.gii', con_idx));
                alt_out2_gii = fullfile(stats_folder, sprintf('TFCE_log_pFWE_%04d.gii', con_idx));
                alt_out3_gii = fullfile(stats_folder, sprintf('TFCE_log_p_%04d.gii', con_idx));
                alt_out4_gii = fullfile(stats_folder, sprintf('TFCE_log_pFDR_%04d.gii', con_idx));
                
                % Retry check a few times if not found immediately
                for retry = 1:3
                    alt_ok = exist(alt_out1, 'file') || exist(alt_out2, 'file') || exist(alt_out3, 'file') || exist(alt_out4, 'file') || ...
                             exist(alt_out1_gii, 'file') || exist(alt_out2_gii, 'file') || exist(alt_out3_gii, 'file') || exist(alt_out4_gii, 'file');
                    if tfce_folder_ok || alt_ok
                        break;
                    end
                    if retry < 3
                        fprintf('        ... waiting for file system (%ds) ...\n', retry);
                        pause(2);
                        % Re-check folder
                        tfce_folder_ok = exist(tfce_folder, 'dir') && (exist(fullfile(tfce_folder, 'logP_max.nii'), 'file') || exist(fullfile(tfce_folder, 'logP_max.gii'), 'file'));
                    end
                end

                if tfce_folder_ok || alt_ok
                    if tfce_folder_ok
                        fprintf('        ✓ TFCE complete (outputs in %s)\n\n', tfce_folder);
                    else
                        % Report which alternative file was found
                        if exist(alt_out2, 'file')
                            found = alt_out2;
                        elseif exist(alt_out4, 'file')
                            found = alt_out4;
                        elseif exist(alt_out3, 'file')
                            found = alt_out3;
                        elseif exist(alt_out1, 'file')
                            found = alt_out1;
                        elseif exist(alt_out2_gii, 'file')
                            found = alt_out2_gii;
                        elseif exist(alt_out4_gii, 'file')
                            found = alt_out4_gii;
                        elseif exist(alt_out3_gii, 'file')
                            found = alt_out3_gii;
                        else
                            found = alt_out1_gii;
                        end
                        fprintf('        ✓ TFCE complete (found alternative output: %s)\n\n', found);
                    end
                    tfce_success = tfce_success + 1;
                else
                    fprintf('        ⚠ TFCE run finished but expected outputs not found. Trying fallback (Freedman-Lane)...\n');
                    % Fallback: set Freedman-Lane nuisance handling (1)
                    try
                        matlabbatch{1}.spm.tools.tfce_estimate.nuisance_method = 1;
                        fallback_file = fullfile(logs_dir, sprintf('tfce_prepared_batch_contrast_%04d.fallback.mat', con_idx));
                        save(fallback_file, 'matlabbatch');
                        fprintf('        Saved fallback prepared batch to: %s\n', fallback_file);
                    catch MEsavefb
                        fprintf('        ⚠ Could not save fallback batch: %s\n', MEsavefb.message);
                    end
                    try
                        spm_jobman('run', matlabbatch);
                        
                        % Wait for filesystem
                        pause(2);
                        
                        % re-check both folder and alternative files
                        tfce_folder_ok_fb = exist(tfce_folder, 'dir') && exist(fullfile(tfce_folder, 'logP_max.nii'), 'file');
                        
                        % Retry loop for fallback
                        for retry = 1:3
                            alt_ok_fb = exist(alt_out1, 'file') || exist(alt_out2, 'file') || exist(alt_out3, 'file') || exist(alt_out4, 'file');
                            if tfce_folder_ok_fb || alt_ok_fb
                                break;
                            end
                            if retry < 3
                                pause(2);
                                tfce_folder_ok_fb = exist(tfce_folder, 'dir') && exist(fullfile(tfce_folder, 'logP_max.nii'), 'file');
                            end
                        end

                        if tfce_folder_ok_fb || alt_ok_fb
                            if tfce_folder_ok_fb
                                fprintf('        ✓ TFCE complete after Freedman-Lane fallback (outputs in %s)\n\n', tfce_folder);
                            else
                                % report which alternative file was found
                                if exist(alt_out2, 'file')
                                    foundfb = alt_out2;
                                elseif exist(alt_out4, 'file')
                                    foundfb = alt_out4;
                                elseif exist(alt_out3, 'file')
                                    foundfb = alt_out3;
                                else
                                    foundfb = alt_out1;
                                end
                                fprintf('        ✓ TFCE complete after Freedman-Lane fallback (found alternative output: %s)\n\n', foundfb);
                            end
                            tfce_success = tfce_success + 1;
                        else
                            fprintf('        ✗ Fallback run completed but outputs still missing\n\n');
                            tfce_failed = tfce_failed + 1;
                        end
                    catch MEfb
                        fprintf('        ✗ TFCE fallback (Freedman-Lane) failed: %s\n\n', MEfb.message);
                        tfce_failed = tfce_failed + 1;
                    end
                end

            catch MEsb
                fprintf('        ✗ TFCE failed during spm_jobman run: %s\n', MEsb.message);
                fprintf('        ✗ Attempting Freedman-Lane fallback...\n');
                % Attempt fallback with Freedman-Lane nuisance method
                try
                    matlabbatch{1}.spm.tools.tfce_estimate.nuisance_method = 1;
                    fallback_file = fullfile(logs_dir, sprintf('tfce_prepared_batch_contrast_%04d.fallback.mat', con_idx));
                    save(fallback_file, 'matlabbatch');
                    fprintf('        Saved fallback prepared batch to: %s\n', fallback_file);
                catch MEsavefb2
                    fprintf('        ⚠ Could not save fallback batch: %s\n', MEsavefb2.message);
                end
                try
                    spm_jobman('run', matlabbatch);
                    
                    % Wait for filesystem
                    pause(2);
                    
                    % Retry loop for second fallback
                    for retry = 1:3
                        if exist(tfce_folder, 'dir') && exist(fullfile(tfce_folder, 'logP_max.nii'), 'file')
                            break;
                        end
                        if retry < 3
                            pause(2);
                        end
                    end

                    if exist(tfce_folder, 'dir') && exist(fullfile(tfce_folder, 'logP_max.nii'), 'file')
                        fprintf('        ✓ TFCE complete after Freedman-Lane fallback\n\n');
                        tfce_success = tfce_success + 1;
                    else
                        fprintf('        ✗ Fallback run completed but outputs still missing\n\n');
                        tfce_failed = tfce_failed + 1;
                    end
                catch MEfb2
                    fprintf('        ✗ TFCE fallback (Freedman-Lane) failed: %s\n\n', MEfb2.message);
                    tfce_failed = tfce_failed + 1;
                end
            end

        catch MErunprep
            fprintf('        ✗ Error preparing/running TFCE: %s\n\n', MErunprep.message);
            tfce_failed = tfce_failed + 1;
        end

    catch ME
        fprintf('        ✗ TFCE failed: %s\n\n', ME.message);
        tfce_failed = tfce_failed + 1;
    end

    % In pilot mode, stop after the first successful run or 3 attempts
    if pilot_mode
        if tfce_success >= 1
            fprintf('🧪 PILOT MODE: Success! Stopping after 1 contrast.\n');
            break;
        elseif (tfce_failed + tfce_skipped) >= 3
            fprintf('🧪 PILOT MODE: Stopping after 3 failed/skipped attempts.\n');
            break;
        end
    end
end

% Summary
fprintf('%s\n', repmat('═', 1, 80));
fprintf('TFCE CORRECTION SUMMARY\n');
fprintf('%s\n\n', repmat('═', 1, 80));

fprintf('Contrasts processed: %d\n', length(contrasts_to_process));
fprintf('  Success:  %d\n', tfce_success);
fprintf('  Skipped:  %d\n', tfce_skipped);
fprintf('  Failed:   %d\n\n', tfce_failed);

if tfce_success > 0
    fprintf('✓ TFCE correction complete!\n');
    fprintf('\nResults available in:\n');
    fprintf('  %s/TFCE_*/ directories\n', stats_folder);
    fprintf('\nKey files:\n');
    fprintf('  logP_max.nii    - FWE-corrected -log10(p) map\n');
    fprintf('  TFCE_max.nii    - TFCE statistic map\n');
else
    fprintf('⚠ No contrasts were successfully processed\n');
end

fprintf('%s\n', repmat('═', 1, 80));

end
