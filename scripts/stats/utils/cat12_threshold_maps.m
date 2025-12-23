function cat12_threshold_maps(stats_dir, varargin)
% CAT12_THRESHOLD_MAPS - Threshold and transform SPM-maps using CAT12
%
% This function uses the CAT12 "Threshold and transform SPM-maps" tool to
% generate (log-scaled) p-maps or correlation maps from SPM.mat.
%
% Usage:
%   cat12_threshold_maps(stats_dir)
%   cat12_threshold_maps(stats_dir, 'p_unc', 0.001, 'p_fwe', 0.05, 'both', true)
%
% Inputs:
%   stats_dir - Path to SPM.mat directory
%   'p_unc'   - Uncorrected p-value threshold (default: 0.001)
%   'p_fwe'   - FWE corrected p-value threshold (default: 0.05)
%   'both'    - Both directions (default: true)
%   'log'     - Log-scaled p-maps (default: true)

    % Parse inputs
    p = inputParser;
    addRequired(p, 'stats_dir', @ischar);
    addParameter(p, 'p_unc', 0.001, @isnumeric);
    addParameter(p, 'p_fwe', 0.05, @isnumeric);
    addParameter(p, 'both', true, @islogical);
    addParameter(p, 'log', true, @islogical);
    addParameter(p, 'contrast_list', [], @isnumeric);
    addParameter(p, 'cluster_size', 0, @isnumeric); % optional extent threshold in voxels
    parse(p, stats_dir, varargin{:});

    stats_dir = p.Results.stats_dir;
    p_unc = p.Results.p_unc;
    p_fwe = p.Results.p_fwe;
    both = p.Results.both;
    log_scaled = p.Results.log;
    contrast_list = p.Results.contrast_list;
    cluster_k = p.Results.cluster_size;

    fprintf('\n%s\n', repmat('═', 1, 80));
    fprintf('CAT12 DOUBLE THRESHOLDING\n');
    fprintf('%s\n\n', repmat('═', 1, 80));

    spm_file = fullfile(stats_dir, 'SPM.mat');
    if ~exist(spm_file, 'file')
        error('SPM.mat not found in %s', stats_dir);
    end

    fprintf('Settings:\n');
    fprintf('  Stats folder:     %s\n', stats_dir);
    fprintf('  p (uncorrected):  %.3f\n', p_unc);
    fprintf('  p (FWE):          %.3f\n', p_fwe);
    fprintf('  Both directions:  %d\n', both);
    fprintf('  Log-scaled:       %d\n', log_scaled);
    fprintf('  Cluster size k:   %d\n\n', cluster_k);

    % Load SPM.mat to get T-maps
    load(spm_file);

    % If no explicit contrast list was provided, prefer the screening output
    if isempty(contrast_list)
        screening_file = fullfile(stats_dir, 'screening_results.mat');
        if exist(screening_file, 'file')
            try
                load(screening_file, 'significant_contrasts');
                if exist('significant_contrasts', 'var') && ~isempty(significant_contrasts)
                    contrast_list = significant_contrasts;
                    fprintf('Using %d significant contrasts from screening_results.mat\n', numel(contrast_list));
                end
            catch
                fprintf('Warning: Failed to read screening_results.mat. Falling back to all T-contrasts.\n');
            end
        end
    end

    % If still empty, fall back to all contrasts
    if isempty(contrast_list)
        contrast_list = 1:length(SPM.xCon);
        fprintf('No contrast subset provided; using all %d contrasts.\n', length(contrast_list));
    end
    t_maps = {};
    for i = contrast_list(:)'
        if i < 1 || i > length(SPM.xCon)
            fprintf('Warning: Contrast index %d out of range, skipping.\n', i);
            continue;
        end
        % Check if it's a T-contrast
        if strcmp(SPM.xCon(i).STAT, 'T')
            t_maps{end+1} = fullfile(stats_dir, [SPM.xCon(i).Vspm.fname ',1']);
        else
            fprintf('Warning: Contrast %d is not a T-contrast; skipping for double thresholding.\n', i);
        end
    end
    
    if isempty(t_maps)
        error('No T-contrasts found in SPM.mat');
    end

    % Initialize matlabbatch
    matlabbatch{1}.spm.tools.cat.tools.T2x.data_T2x = t_maps';
    
    if log_scaled
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.sel = 2; % Log-scaled p-maps
    else
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.sel = 1; % p-maps
    end

    % Handle threshold
    % Note: CAT12 uses specific field names for common thresholds
    if p_unc == 0.001
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.threshdesc.uncorr.thresh001 = 0.001;
    elseif p_unc == 0.01
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.threshdesc.uncorr.thresh01 = 0.01;
    elseif p_unc == 0.05
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.threshdesc.uncorr.thresh05 = 0.05;
    else
        fprintf('Warning: p_unc = %.4f not explicitly supported by this script version. Using 0.001.\n', p_unc);
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.threshdesc.uncorr.thresh001 = 0.001;
    end

    % Two-sided vs one-sided: CAT12 uses "inverse" flag to capture the opposite tail.
    if both
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.inverse = 1;
    else
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.inverse = 0;
    end

    % Cluster/FWE handling. If an FWE threshold is requested, prefer the CAT12
    % fwe2 branch (voxel-wise FWE) and set non-isotropic smoothing flag.
    if ~isempty(p_fwe) && p_fwe > 0
        if abs(p_fwe - 0.05) < 1e-6
            matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.fwe2.thresh05 = 0.05;
        elseif abs(p_fwe - 0.01) < 1e-6
            matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.fwe2.thresh01 = 0.01;
        elseif abs(p_fwe - 0.001) < 1e-6
            matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.fwe2.thresh001 = 0.001;
        else
            fprintf('Warning: p_fwe = %.4f not explicitly supported; using 0.05.\n', p_fwe);
            matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.fwe2.thresh05 = 0.05;
        end
        matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.fwe2.noniso = 1;
    else
        % Uncorrected cluster extent
        if isempty(cluster_k) || cluster_k <= 0
            matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.none = 1;
        else
            matlabbatch{1}.spm.tools.cat.tools.T2x.conversion.cluster.size = cluster_k;
        end
    end
    matlabbatch{1}.spm.tools.cat.tools.T2x.atlas = 'None';

    % Run the batch
    spm('defaults', 'FMRI');
    spm_jobman('initcfg');
    try
        spm_jobman('run', matlabbatch);
        fprintf('\n✓ Double thresholding complete.\n');
    catch ME
        fprintf('\n❌ Double thresholding failed: %s\n', ME.message);
        rethrow(ME);
    end
end
